---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-14-feat-data-001-deployed-dates-exchange-clock.md
branch: fix/feat-data-001-deployed-dates-exchange-clock
pr: null
status: ready
---

# Deployed code takes "today" from the exchange's clock: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the spec's order, [0] to [8]. The spec's own prose counts them from 1 (its "done_when 2" is [1] here).

**Goal:** The 71 sites of the spec's Appendix A (64 host-clock dates and 7 `CURRENT_DATE` reads, in 39 files) take today's date from `lib.eastern_time.market_today()` or the text `market_today_sql()` returns, so no deployed job, service or library reads tomorrow's date between 19:00 Eastern and midnight.

**Architecture:** Site-by-site replacement with the two helpers that already exist. Each job family gets one test file that freezes one instant through one seam (`tests/fixtures/market_clock.py`) and makes the host clock raise inside the module under test. Two meta tests pin the stage: the written-out lists of the 71 and of the 31 that stay, and the scheduler hours of the jobs whose sites are right only because of when they run. The timezone ratchet's baseline loses exactly the 71 identities.

**Tech Stack:** Python, `lib/eastern_time.py`, pandas, SQLAlchemy `text`, FastAPI `TestClient`, pytest (`monkeypatch`, `subprocess`), `ast`, the repo's `gcp/deploy.sh` reader (`scripts/maintenance/doc_inventory.py`).

**Spec:** docs/superpowers/specs/2026-11-14-feat-data-001-deployed-dates-exchange-clock.md

## Global Constraints

- **Base.** `origin/main` at 161fa992 or later (the spec is `status: approved` there, #1938). This plan file is the branch's first commit, alone. The site-note producer of Task 13 refuses a branch with no committed plan.
- **The sites are Appendix A's rows.** This plan does not repeat them. A task says "Appendix A, family X" and adds only what the appendix leaves open (an import, a spelling). The replacement for a row is its Replacement cell, read with the spec's Design 1. Nothing else in a touched function changes; no site moves from days to sessions.
- **Lines.** Appendix A's lines are for 20d9c47b and hold on 161fa992: none of the 39 files changed in between (`git diff --name-only`, 2026-11-14). If a later merge moves one, find the site by the row's function and expression.
- **The 71, checked.** Planning run of 2026-11-14 on 161fa992 with the ratchet's own scanner: all 71 identities are in the baseline at the file and function Appendix A names; the other baseline entries of the 39 files are exactly the 31 of Appendix B; `current_hits()` equals the committed baseline (313 entries, 139 files). If a merge of `main` changes one of the 71 or the 31, stop that site and tell the owner.
- **Imports.** `from lib.eastern_time import market_today` (and `market_today_sql` where the file has a SQL site) at module level, among the file's `lib` and `gcp` imports and below its `sys.path` line where it has one. A file that already has a module-level `from lib.eastern_time import ...` extends that line. The two files run by path get a function instead (Task 2). A name whose last use is gone (`date`, a function-local `datetime as _dt`) leaves its import only when `grep` shows no other use.
- **Not in the PR's diff:** `tests/meta/test_timezone_boundaries.py`, `lib/eastern_time.py`, `gcp/deploy.sh`, `.github/`, Dockerfiles, `gcp/schema.sql`, `platform/api/openapi.json`, `CLAUDE.md`, and the held files of the spec's Non-goals, among them `gcp/fetchers/fetch_alphavantage_intraday.py` (Decision 4) and `scripts/replay_signal_monitor.py` (Decision 5). In `gcp/signal_monitor.py` only `fetch_latest_bar` changes.
- **No `# tz-ok:` is added and the 31 of Appendix B stay.** A site that turns out to be UTC by contract is taken out of the stage in the PR, with the reason, and the owner is told (spec, Design 5). No stored row, schedule, job definition or `TZ` changes. No fallback is added (CLAUDE.md 3.7).
- **Words used in the test steps.** `E` is the Eastern date at the frozen instant. "Recording" is a stub that keeps its arguments. "The four instants" are `STANDARD_INSTANTS` of Task 1. A test freezes with `freeze_market_clock(monkeypatch, instant, <module under test>)` unless the step names more.
- **Red then green, on the PR.** Every family test file is run three times and the output kept:
  1. on the unmodified code: the cases fail with `HostClockRead`, whose message names the file and line of the read;
  2. on the unmodified code with `MARKET_CLOCK_HOST=utc`: the evening cases fail showing the value `main` gives, and the daytime cases pass. This is the record of the pre-change value (spec, Design 4);
  3. after the change, with and without the variable: all pass.
- **Existing tests.** A test that stubs a module's `date` or `datetime` for a changed site moves to the seam. A test that builds its expectation from the host's `date.today()` or `datetime.now()` for a changed site reads `lib.eastern_time.market_today()` instead: CI runs in UTC, so from 00:00 to 05:00 UTC the two dates differ and such a test would fail by the hour. Each task names what the planning scan found; the suite decides the rest. Every existing test edited goes on the list of Task 12, with its reason.
- **The render step.** The generated inventory cites 44 lines of `platform/api/main.py`, three routers and `gcp/discord_interactions/main.py`, and an added import moves them. A task that changes code runs
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed; about a minute), and stages whichever doc changed in the same commit. The inventory blocks are never edited or merged by hand; after any merge of `main`, render again.
- **The baseline step.** The ratchet fails when a baselined site no longer occurs, so a task that removes sites regenerates the baseline in the same commit: `python -m tests.meta.test_timezone_boundaries --write-baseline`, then `python3 -m pytest tests/meta/test_timezone_boundaries.py -q` (expect all pass; a "New market-time relabel" means a replacement was written with a flagged pattern: fix the code, not the baseline), then count what left, against `HEAD`:
  `python3 -c "import json,subprocess,sys;from collections import Counter;p='tests/fixtures/timezone_boundary_baseline.json';f=lambda d:Counter((a,r,i) for a in d for r in d[a] for i in d[a][r]);o=f(json.loads(subprocess.run(['git','show',sys.argv[1]+':'+p],capture_output=True,text=True,check=True).stdout));n=f(json.load(open(p)));print(sum((o-n).values()),sum((n-o).values()))" HEAD`
  Expect the task's count and `0`. Counts: Task 2, 13; Task 3, 5; Task 4, 11; Task 5, 10; Task 6, 7; Task 7, 9; Task 8, 8; Task 9, 1; Task 10, 7. They sum to 71.
- **The site snapshot is last.** It stops verifying whenever `main` moves or a watched file changes. The site notes and the snapshot are the last two commits before the final push; all four site-note steps of Task 13 are redone after any merge of `main`.
- **Draft until closed.** The PR is opened as a draft and stays one until the close commits of Task 13 and the final body are pushed. Marking it ready starts the first of two review rounds; there is no third.
- **Commits:** `python3 scripts/gate/spec_gate.py --commit` first. Conventional message, imperative, 72 characters or fewer. No AI attribution of any kind. Never rebase or force-push after the first push; merge `origin/main` to catch up. Judge the suite by `make test` (it runs with `-x`), not by a folder run. Tests go in the files named, never at the `tests/` root.
- **A claim** in a doc or on the PR about what the code does comes from output that was run (CLAUDE.md 3.11.1). This plan says where it ran something and where it only read.
- **Other lanes** (open PRs read on 2026-11-14; if one has merged, merge `origin/main` before the task named and rerun that task's tests):
  - The premarket brief fix (`fix/feat-playbook-001-brief-market-date`) removes three entries of `gcp/premarket_brief.py` from the baseline; #1914 and #1430 edit the baseline too, and #1430 (draft) edits five family A and G files. Before Tasks 2 and 8. A baseline conflict is resolved by regenerating, never by hand.
  - #1916 edits `lib/agents/summarizers.py` and `platform/api/routers/grid.py`; #1845, #1832 and #1823 edit `gcp/signal_monitor.py`. Before Tasks 6, 8 and 10.
  - #1671 edits `gcp/deploy.sh`, which Task 11 reads. Before Task 11.
  - The bucket copy and the 410 routes (#1937) add rows to the same notes table and regenerate the same snapshot. Before Task 13.
- **Choices this plan makes where the spec leaves one open** (reported to the owner with the plan):
  - "One fixture" is one function taking `monkeypatch`, in the style of the other modules under `tests/fixtures/`, not a registered pytest fixture.
  - The fixture has a second mode, `MARKET_CLOCK_HOST=utc`, in which a guarded name answers as a UTC container does. It exists so the first run on `main` shows the pre-change value. The default, and the only mode CI runs, raises.
  - `HostClockRead` derives from `BaseException`: several functions under test wrap their body in `except Exception` (`fetch_unusual_whales_earnings`, `fetch_latest_bar`, API handlers), which would swallow an ordinary exception and let the test pass on unmodified code.
  - The fixture can also guard the `datetime` module (`stdlib=True`) and `pd.Timestamp` (`pandas=True`), because three of the 71 read the clock through a function-local import and two through `pd.Timestamp.utcnow()`; and it can let one named call text through (`allow_instants`), because two stage 1 sites share a function with an Appendix B instant that stays. Only the tests that name these pass them.
  - The run-hours test reads `gcp/deploy.sh` through `scripts.maintenance.doc_inventory`, not a new parser. A reader of `_schedule*` lines written for this plan missed two of the 65 entries (`sec-filings-intraday`, declared inside an `if`, and `backfill-indicators-weekly`, a raw `gcloud scheduler jobs create`); the repo's reader finds both.
  - The site of `scripts/fetch_catalyst_calendar.py` (family F) is done in Task 2, where done_when[1] needs its path-run check. Families D, E and F get test files the spec does not name (Tasks 5 to 7).
  - The baseline is regenerated in each family's commit, not once at the end, so no commit leaves the ratchet red. "Removes exactly the 71 and adds no line" is judged by identity (spec, Design 5): the file is JSON, and removing the last entry of a list rewrites the line above it.
  - Existing tests the spec does not list are edited (Tasks 2, 3, 5; found by running): the SQLite adapters learn the helper's text, and two assertions on the literal `CURRENT_DATE` change.
  - `lib/indicators.py` and `lib/trading_analysis.py` combine with `datetime(2000, 1, 1)`.

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | the baseline loses exactly the 71; the stage-one lists; the ratchet unmodified and green | 2 to 12 |
| [1] | the three earnings scopes, the option targets, the snapshot, the two files run by path | 2 |
| [2] | `calculation_date`; the watchlist's date and SQL | 3 |
| [3] | the AV range end; the two builders' window | 4 |
| [4] | the API routes, the Discord date argument, the library defaults | 8, 9, 10 |
| [5] | the 1,587 hours; the run hours of the "no" jobs | 1, 11 |
| [6] | every test through the one fixture, with the daytime value; no opt-out added | 1 to 10, 12 |
| [7] | `make test`; the list of changed tests; the measured query | 12, 13 |
| [8] | product record, site notes, snapshot, audit, gate | 13 |

## Review Focus

Inputs the spec implies and no done_when test pins. Each has a test in the task that owns the code.

- A test run between 00:00 and 05:00 UTC: an existing test that computes its expectation from the host's `date.today()` now disagrees with the code by one day. No test this PR edits may read the host clock. Tasks 11 and 12.
- A variable that was a `datetime` and is now a `date` (`today` in two catalyst routes, the catalyst script, the weekend review): every later use must give the same `YYYY-MM-DD` text. Tasks 2, 6 and 8.
- The helper's SQL text inside a statement that already has bind names and `::` casts: the statement keeps exactly the bind names it had. Tasks 2, 3, 5 and 7.
- The two Sundays the clocks change (2026-03-08, 2026-11-01), and a `PIPELINE_SCOPE` that is set but is not a scope (`monthly`): `weekly` on both Sundays, and the unknown value falls through to the clock. Task 2.
- A caller that passes its own date (`today=`, `as_of=`, `--end-date`) in the evening: the passed date is used. Tasks 4, 8, 9 and 10.

## Task 1: The clock seam and the hour count

Spec: Design 3 ("One seam", "The host clock is forbidden in the same test"); Tests. Advances done_when[5] (first sentence), [6]. Needs: nothing. No production code changes.

**Files:** Create `tests/fixtures/market_clock.py`, `tests/lib/test_market_clock_fixture.py`, `tests/lib/test_market_today_hours.py`.

**Interfaces:** Produces, in `tests/fixtures/market_clock.py`:
- `HOST_ENV = "MARKET_CLOCK_HOST"`; `class HostClockRead(BaseException)`.
- `DAYTIME = "2026-11-12T15:00:00Z"` (Thursday 10:00 EST).
- `STANDARD_INSTANTS: tuple[tuple[str, date], ...]`, each instant with the Eastern date at it: `("2026-11-14T01:30:00Z", date(2026, 11, 13))` (Friday 20:30 EST), `("2026-07-10T23:30:00Z", date(2026, 7, 10))` (Friday 19:30 EDT; the host date agrees), `("2026-07-11T00:30:00Z", date(2026, 7, 10))` (Friday 20:30 EDT), `(DAYTIME, date(2026, 11, 12))`.
- `freeze_market_clock(monkeypatch, instant: str, *modules: ModuleType, stdlib: bool = False, pandas: bool = False, allow_instants: tuple[str, ...] = ()) -> datetime`, returning the frozen instant, aware, UTC.

The rules the signature does not determine:
- `instant` is ISO text with a `Z` or an offset; none raises `ValueError`.
- `lib.eastern_time.eastern_now` and `utc_now` are replaced through `monkeypatch` and return the instant. Nothing else in that module is touched, so `market_today()` follows.
- In each module passed, every module-level name bound to the real `datetime.datetime` or `datetime.date` class becomes a guard subclass. On the guard, `today()`, `utcnow()` and `now()` with no zone are host reads; `now(tz)` returns the frozen instant in that zone; the rest is inherited. A metaclass makes `isinstance` and `issubclass` answer as the real class does.
- A host read raises `HostClockRead` naming the call and the caller's file and line. With `MARKET_CLOCK_HOST=utc` it returns the frozen instant as naive UTC (a `date` for `date.today()`); any other value of the variable raises `ValueError`.
- `stdlib=True` also replaces `datetime.datetime` and `datetime.date` on the `datetime` module (for imports made inside a function). `pandas=True` guards `pd.Timestamp.now`, `utcnow` and `today` the same way.
- `allow_instants` holds call texts such as `"datetime.now().isoformat()"`. A host read whose calling source line (`linecache`) contains one returns the frozen naive UTC instant. It is for an Appendix B instant that shares a function with a stage 1 site, and nothing else.

Prototyped on 2026-11-14 in the planning scratch, on 58d96807 (the 39 files are the same on 161fa992) and on a copy with family A changed. On the changed copy every prototype case passed in both modes. On the unmodified tree the family A cases failed with `HostClockRead` by default and, with `MARKET_CLOCK_HOST=utc`, only the winter evening cases failed, each with the value the spec's Design 4 table gives for `main`. A read inside `try: ... except Exception:` still raised; `TestClient` re-raised a handler's `HostClockRead` as itself; a `TestClient` request ran under `stdlib=True, pandas=True` with no host read from the framework.

- [ ] Write `tests/lib/test_market_clock_fixture.py`, with `mod` a `types.ModuleType` holding `date` and `datetime`:
  - `test_the_seam_moves_market_today`: at `2026-11-09T00:00:30Z`, `market_today() == date(2026, 11, 8)` and `utc_now()` is the returned instant; and for each pair of `STANDARD_INSTANTS`, `market_today()` is its date.
  - `test_a_host_read_raises_and_an_aware_read_is_frozen`: `mod.date.today()`, `mod.datetime.now()`, `mod.datetime.utcnow()`, `mod.datetime.today()` each raise `HostClockRead`; `mod.datetime.now(ET).date() == date(2026, 11, 8)`; `mod.datetime.strptime` and `mod.date.fromisoformat` work; `isinstance(datetime(2026, 1, 1), mod.datetime)`.
  - `test_function_local_imports_and_pandas_are_guarded_on_request`: with `stdlib=True, pandas=True`, a function doing `from datetime import date as _d; _d.today()` raises, `pd.Timestamp.utcnow()` raises, `pd.Timestamp.now(tz="America/New_York").date()` is the Eastern date, `pd.to_datetime("2026-01-02")` works.
  - `test_host_utc_mode_answers_as_a_utc_container` (`monkeypatch.setenv`): at `2026-11-09T00:00:30Z`, `mod.date.today() == date(2026, 11, 9)` while `market_today() == date(2026, 11, 8)`.
  - `test_a_swallowing_block_cannot_hide_a_host_read`: `try: mod.datetime.now()` / `except Exception: ...` still raises `HostClockRead`, and the message holds this test file's name.
  - `test_an_allowed_instant_is_let_through`: with `allow_instants=("mod.datetime.now().isoformat()",)`, the line `stamp = mod.datetime.now().isoformat()` returns the frozen naive UTC text and the line `d = mod.datetime.now().date()` still raises.
  - `test_bad_input_is_refused`: an instant with no zone, and `MARKET_CLOCK_HOST=local`, each raise `ValueError`.
  - `test_no_committed_file_sets_the_host_mode`: the variable is not in `os.environ`, and its name is absent from `Makefile`, `tests/conftest.py`, `pytest.ini` and `pyproject.toml` where they exist, and from every file under `.github/workflows/`.
- [ ] Write `tests/lib/test_market_today_hours.py`: `test_the_exchange_date_differs_from_the_utc_date_at_1587_hours_of_2026` freezes every hour from `2026-01-01T00:00Z` to `2026-12-31T23:00Z` and asserts 8,760 hours, 1,587 where `market_today()` differs from the UTC date, at UTC hours `{0, 1, 2, 3}` where `eastern_now().utcoffset()` is minus 4 hours and `{0, 1, 2, 3, 4}` where it is minus 5. `test_the_two_clock_change_days` (Review Focus): `2026-11-01` at `2026-11-01T05:30:00Z` and at `2026-11-02T04:59:00Z`; `2026-03-08` at `2026-03-08T06:30:00Z`.
- [ ] Run: `python3 -m pytest tests/lib/test_market_clock_fixture.py tests/lib/test_market_today_hours.py -q` (expect FAIL: no `tests.fixtures.market_clock`).
- [ ] Implement `tests/fixtures/market_clock.py`.
- [ ] Run again (expect all pass; the planning run of the hour count gave 8,760 and 1,587).
- [ ] Commit: `test(data): add the frozen market clock and the 1,587-hour count`

## Task 2: Family A, the evening earnings refresh, and the two files run by path

Spec: Design 1; Design 2; Appendix A, family A, and `scripts/fetch_catalyst_calendar.py:618` of family F; Problem rows 1 and 2. Advances done_when[0], [1], [6]. Needs: Task 1.

**Files:** Modify `scripts/fetch_earnings_calendar.py`, `scripts/fetch_catalyst_calendar.py`, `gcp/fetchers/fetch_earnings_history.py`, `gcp/fetchers/compute_earnings_reactions.py`, `tests/gcp/test_ew_fetcher_reader_retirement.py`. Create `tests/scripts/test_fetch_earnings_calendar_evening.py`, `tests/gcp/test_earnings_scope_evening.py`.

**Interfaces:** Produces `_market_today() -> date` in each of the two scripts: it puts the repo root (`Path(__file__).resolve().parent.parent`) on `sys.path` if absent, imports `market_today` from `lib.eastern_time` inside the function, and returns its value. Neither script gains a module-level import of `lib` or `gcp`.

What Appendix A leaves open:
- In the two scripts every Replacement cell's `market_today()` is spelled `_market_today()`. `_previous_trading_weekday` itself is not edited (Decision 2). `scripts/fetch_catalyst_calendar.py` adds `date` to its `datetime` import for the annotation.
- The two `_resolve_scope` twins lose their function-local `from datetime import datetime as _dt`. `fetch_earnings_history.py` extends its `from lib.eastern_time import ET_NAME`; `compute_earnings_reactions.py` gains the import.
- In every SQL site of this plan, each `CURRENT_DATE` of the statement becomes `{market_today_sql()}` inside the f-string.

Executed for this plan on a scratch copy with exactly these edits: `python scripts/fetch_earnings_calendar.py --help` and `python scripts/fetch_catalyst_calendar.py --help` from the repo root with `PYTHONPATH` unset exit 0; each file loaded by path under `python -I` from another directory, with only `scripts/` added to `sys.path`, prints a date from `_market_today()`; the variant with the import at module level exits 1 with `ModuleNotFoundError: No module named 'lib'`. The scanner then reports these 13 identities gone and none new.

- [ ] Write `tests/scripts/test_fetch_earnings_calendar_evening.py` (`import scripts.fetch_earnings_calendar as fec`; `PIPELINE_SCOPE` deleted unless a test sets it):
  - `test_scope_reads_the_exchange_weekday`: `fec._resolve_scope(None)` is `weekly` at `2026-11-09T00:00:30Z` (Sunday 19:00 EST) and at `2026-10-25T23:00:30Z` (Sunday 19:00 EDT), `daily` at `2026-11-03T00:01:00Z` and at `DAYTIME`.
  - `test_scope_on_the_two_clock_change_sundays` (Review Focus): `weekly` at `2026-11-02T00:00:30Z` and at `2026-03-08T23:00:30Z`.
  - `test_the_flag_and_the_variable_still_decide`: on the winter Sunday, `_resolve_scope("daily")` and `PIPELINE_SCOPE=daily` give `daily`; on the Monday instant `PIPELINE_SCOPE=weekly` gives `weekly`; on the winter Sunday `PIPELINE_SCOPE=monthly` gives `weekly` (Review Focus).
  - `test_av_option_targets`, the ISO dates of `_resolve_target_dates_for_av_options(_resolve_scope(None))`: `2026-11-09T00:00:30Z` gives `2026-11-09` to `2026-11-13`; `2026-11-03T00:01:00Z` gives `["2026-11-03"]`; `2026-11-06T00:00:30Z` gives `["2026-11-06"]`; `2026-11-07T00:00:30Z` gives `[]`; `2026-10-26T23:00:00Z` gives `["2026-10-27"]`; `DAYTIME` gives `["2026-11-13"]`.
  - `test_main_hands_the_previous_weekday_and_the_exchange_windows`, over `("2026-11-03T00:01:00Z", "2026-10-30")`, `("2026-11-06T00:00:30Z", "2026-11-04")`, `("2026-11-09T00:00:30Z", "2026-11-06")`, `(DAYTIME, "2026-11-11")`: `sys.argv` `["x", "--source", "yh"]`, `ALPHA_VANTAGE_API_KEY=k`; stubs shaped as `tests/scripts/test_fetch_earnings_calendar_sources.py::test_source_all_calls_only_av_uw_and_yahoo` shapes them: `fec.fetch_yahoo_earnings` recording, returning one Yahoo row a day from `E - 3` to `E + 10`; `fec.enrich_with_av_options` recording `snapshot_date` and the frame's dates, returning the frame; `fec.persist_to_cloud_sql` returning 1. Assert the snapshot is the paired text, the Yahoo call was `(E - 1 day, E + 7 days)`, the enrichment saw dates from `E - 1` to `E + 7` only, and `main()` returns (so `print_summary` made no host read).
  - `test_unusual_whales_window_ends_seven_days_from_the_exchange_date`, at `2026-11-14T01:30:00Z` and `DAYTIME`, frozen with `allow_instants=("datetime.now().isoformat()",)` (the stamp at `:1069` stays): `fec.requests.get` answers items with `report_date` `E + 7 days` and `E + 8 days`; `fetch_unusual_whales_earnings(days_ahead=7)` returns the first only.
  - `test_main_counts_a_hand_window_from_the_exchange_date`: at `2026-11-14T01:30:00Z`, `--source uw --start-date 2026-11-13 --end-date 2027-02-21 --no-av-options-enrich`, `EarningsCalendarFetcher.fetch_unusual_whales_earnings` recording and returning one row dated `2026-11-13`: `days_ahead == 100` (99 from the host date).
  - `test_the_file_runs_as_the_job_runs_it`, over the two script names: `[sys.executable, f"scripts/{name}.py", "--help"]` with `cwd=REPO` and `PYTHONPATH` removed from the environment returns 0; and `[sys.executable, "-I", "-c", code]` with `cwd=tmp_path`, where `code` inserts `REPO / "scripts"` into `sys.path`, asserts the repo root is not on it and `lib` is not in `sys.modules`, loads the file with `importlib.util.spec_from_file_location` and prints `mod._market_today().isoformat()`, returns 0 with output matching `^\d{4}-\d{2}-\d{2}$`.
  - `test_catalyst_main_asks_for_the_exchange_window`, over the four instants (`import scripts.fetch_catalyst_calendar as fcc`): `get_api_key` returns `"k"`, `fetch_all_catalysts` recording and returning `[]`, `save_catalysts` returning `[]`: the recorded window is `(E - 3 days).isoformat()` to `(E + 14 days).isoformat()`, each ten characters (Review Focus).
- [ ] Write `tests/gcp/test_earnings_scope_evening.py`: `test_the_history_and_reactions_scopes_read_the_exchange_weekday`, over the two modules and the four cases of `test_scope_reads_the_exchange_weekday`, frozen with `stdlib=True`. `test_the_history_window_sql_reads_the_exchange_date`: with `gcp.database.query_to_dataframe` recording, the statement of `fetch_earnings_history._earnings_calendar_tickers` holds `market_today_sql()` twice, no `CURRENT_DATE`, and `set(sqlalchemy.text(sql)._bindparams)` equal to what the unmodified code gives (record it first; Review Focus).
- [ ] Run the three runs of "Red then green". Planning run on the unmodified tree with `MARKET_CLOCK_HOST=utc`: `daily` for all three scopes on the winter Sunday; targets `["2026-11-10"]` that Sunday, `["2026-11-04"]` on the Monday, `[]` on the Thursday; two Unusual Whales rows in the evening; summer and daytime cases pass.
- [ ] Implement.
- [ ] Run: `python3 -m pytest tests/scripts/test_fetch_earnings_calendar_evening.py tests/gcp/test_earnings_scope_evening.py tests/scripts/test_fetch_earnings_calendar_sources.py tests/gcp/test_fetch_earnings_history.py tests/gcp/test_compute_earnings_reactions.py tests/gcp/test_ew_fetcher_reader_retirement.py -q`. Expect `test_actual_reader_retains_controls_and_removes_both_aliases[history_universe]` to fail on `untranslated PostgreSQL construct '::'` (seen in the planning run): the adapter at `test_ew_fetcher_reader_retirement.py:62` replaces only the upper-case `(NOW() AT TIME ZONE 'America/New_York')::date`. Make that line a case-insensitive `re.sub` of the same text; expect all pass.
- [ ] Variant for the record: in a scratch edit, import `lib.eastern_time` at module level in `scripts/fetch_earnings_calendar.py`; expect `test_the_file_runs_as_the_job_runs_it` to fail with `No module named 'lib'`; revert.
- [ ] The render step and the baseline step (13).
- [ ] Commit: `fix(data): read the exchange's date in the evening earnings refresh`

## Task 3: Family B, the Sunday sweep, the watchlist and the views

Spec: Design 1; Appendix A, family B; Problem rows 3 and 4; Risks ("The Python date and the SQL date of one job disagree"). Advances done_when[0], [2], [6]. Needs: Task 1.

**Files:** Modify `scripts/backtest_playability.py`, `gcp/earnings_long_watchlist.py`, `gcp/refresh_earnings_views.py`, `tests/fixtures/earnings_calendar_sources.py`, `tests/gcp/test_earnings_long_watchlist_freshness.py`, `tests/gcp/test_earnings_long_watchlist_sources.py`, `tests/gcp/test_refresh_earnings_views_sources.py`, `tests/integration/test_earnings_daily_path_persistence.py`. Create `tests/scripts/test_backtest_playability_calculation_date.py`, `tests/gcp/test_earnings_long_watchlist_evening.py`.

- [ ] Write `tests/scripts/test_backtest_playability_calculation_date.py::test_calculation_date_is_the_exchange_date`, over `("2026-11-09T01:30:00Z", date(2026, 11, 8))` (Sunday 20:30 EST), `("2026-07-13T00:30:00Z", date(2026, 7, 12))` (Sunday 20:30 EDT), `("2026-07-12T23:30:00Z", date(2026, 7, 12))`, `(DAYTIME, date(2026, 11, 12))`. Inputs: five prediction rows, `ticker` `T1` to `T5`, `score` 1.0 to 5.0, `reported_date` `2026-10-20`, `d_minus_1_close` 100.0, `d_plus_1_close` 104.0, `actual_gap_pct` 4.0, `archetype` `None`; an options frame of one row a ticker (`symbol`, `snapshot_date` `2026-10-19`); `_select_atm_pair` patched to return `{"strike": 100.0, "call_mid": 2.0, "put_mid": 2.0}` and `_select_delta_n_pair` to return `None`. Assert both returned lists are non-empty, then that the set of their `calculation_date` values is `{want}`. (Planning run, unmodified tree, `MARKET_CLOCK_HOST=utc`: these inputs reach the stamp and give `2026-11-09` and `2026-07-13`, both Mondays.)
- [ ] Write `tests/gcp/test_earnings_long_watchlist_evening.py` (`import gcp.earnings_long_watchlist as wl`):
  - `test_main_dates_the_post_and_the_source_age_from_the_exchange_date`: at `2026-11-09T00:45:00Z` (Sunday 19:45 EST), `is_cloud_sql_configured` true, `_latest_source_date` returning `date(2026, 10, 25)` (14 days before 2026-11-08, 15 before 2026-11-09), `_query_watchlist` returning an empty frame, `build_discord_message` recording and returning `{}`: `main(["--dry-run"])` returns 0 and the recorded `as_of` is `date(2026, 11, 8)`. The same at `2026-10-25T23:45:00Z` with source `date(2026, 10, 11)` (`as_of` 2026-10-25) and at `DAYTIME` with source `date(2026, 10, 29)` (`as_of` 2026-11-12).
  - `test_the_watchlist_sql_reads_the_exchange_date`: with `wl.query_to_dataframe_strict` recording, the statement of `_query_watchlist(7, 2)` holds `market_today_sql()` twice, no `CURRENT_DATE`, and `set(sqlalchemy.text(sql)._bindparams) == {"days_ahead", "min_wins"}` (Review Focus).
- [ ] Run the three runs of "Red then green". Expect on the unmodified tree with `MARKET_CLOCK_HOST=utc`: the winter watchlist case returns 1 (the source reads 15 days old); the two evening playability cases give Mondays.
- [ ] Implement Appendix A, family B.
- [ ] In `tests/fixtures/earnings_calendar_sources.py`, add one entry at the head of `_REWRITES`: the text `market_today_sql()` returns (`re.escape`, case-insensitive) becomes `CURRENT_DATE`, so the entries below apply as before. Planning run on a scratch copy with the seven SQL sites changed: without it 11 tests of `test_earnings_long_watchlist_sources.py`, `test_refresh_earnings_views_sources.py` and `test_refresh_earnings_views_retired_score.py` fail on `untranslated PostgreSQL construct '::'`; with it they pass, as do the other files that import the fixture (180 passed).
- [ ] In `test_earnings_long_watchlist_freshness.py`, the four `monkeypatch.setattr(watchlist, "date", Mock(today=...))` stubs (`:28`, `:42`, `:62`, `:95`) become `freeze_market_clock(monkeypatch, "2026-08-30T16:00:00Z", watchlist)`; the asserted dates do not change. `TODAY = date.today()` (`test_earnings_long_watchlist_sources.py:25`, `test_refresh_earnings_views_sources.py:26`) becomes `market_today()`.
- [ ] `tests/integration/test_earnings_daily_path_persistence.py` (`:282`, `:291`) seeds and reads with `CURRENT_DATE`: both become the helper's text. It needs a live Postgres: run `make test-integration` if one is available, else say on the PR it was changed by reading and not run.
- [ ] Run: `python3 -m pytest tests/scripts/test_backtest_playability_calculation_date.py tests/scripts/test_calibrate_earnings.py tests/gcp/test_earnings_long_watchlist_evening.py tests/gcp/test_earnings_long_watchlist_freshness.py tests/gcp/test_earnings_long_watchlist_sources.py tests/gcp/test_refresh_earnings_views_sources.py tests/gcp/test_refresh_earnings_views_retired_score.py tests/agents/test_ranker.py tests/agents/test_earnings_reader_api.py tests/api/test_catalyst_source_labels.py -q` (expect all pass).
- [ ] The render step and the baseline step (5).
- [ ] Commit: `fix(data): date the Sunday sweep and the watchlist by the exchange`

## Task 4: Family C, the AV options nightly and the option builders

Spec: Design 1; Design 3 ("The I/O shape"); Appendix A, family C; Problem rows 5 and 6. Advances done_when[0], [3], [6]. Needs: Task 1.

**Files:** Modify `gcp/fetchers/fetch_av_historical_options.py` (its `from lib.eastern_time import sessions_between` is extended), `gcp/fetchers/build_options_daily_features.py`, `gcp/build_options_daily_greeks.py`, `gcp/build_realtime_gex.py`, `tests/gcp/test_fetch_av_historical_options.py`. Create `tests/gcp/test_evening_windows.py`.

- [ ] Write `tests/gcp/test_evening_windows.py`:
  - `test_from_latest_ends_on_the_exchange_date`: `sys.argv` `["x", "--tickers", "SPY", "--from-latest"]`, `AV_API_KEY=k`, `mod.is_cloud_sql_configured` true, `gcp.database.query_to_dataframe` returning one row (`ticker` `SPY`, `d` the watermark), `mod.process_ticker` recording, `time.sleep` patched to return at once. The fetched dates: `["2026-11-12"]` at `2026-11-13T02:00:00Z` (Thursday 21:00 EST) with watermark `2026-11-11`; `["2026-07-09"]` at `2026-07-10T01:00:00Z` (Thursday 21:00 EDT) with `2026-07-08`; `["2026-11-11", "2026-11-12"]` at `DAYTIME` with `2026-11-10`.
  - `test_an_empty_table_starts_on_the_exchange_date`: at `2026-11-13T02:00:00Z`, `_resolve_start_from_latest([])`, and `_resolve_start_from_latest(["SPY"])` with an empty frame, return `date(2026, 11, 12)`.
  - `test_an_end_date_passed_by_hand_is_used` (Review Focus): at `2026-11-13T02:00:00Z`, `--start-date 2026-11-10 --end-date 2026-11-10` fetches `["2026-11-10"]`.
  - `test_the_incremental_window_is_seven_days_back_from_the_exchange_date`: `build_options_daily_features.main` at `2026-11-13T03:00:00Z` and `build_options_daily_greeks.main` at `2026-11-13T04:15:00Z` (Thursday 22:00 and 23:15 EST), `sys.argv` `["x", "--incremental", "--days=7"]`, the engine getter patched (`mod.get_engine`; for greeks `gcp.database.get_engine`), `build_materialized` and `build` recording: `since == "2026-11-05"` and `until == "2026-11-12"` on every call, and the same at `DAYTIME`.
  - `test_realtime_gex_window`, over the four instants, `--incremental --days=3`, `build_realtime_gex.build` recording: `until` is `E`, `since` is `E - 3 days`.
- [ ] Run the three runs of "Red then green". Expect on the unmodified tree with `MARKET_CLOCK_HOST=utc`: the AV run fetches `["2026-11-12", "2026-11-13"]`; the two builders pass `2026-11-06` and `2026-11-13`.
- [ ] Implement Appendix A, family C.
- [ ] In `tests/gcp/test_fetch_av_historical_options.py`, `assert out == date.today()` (`:459`, `:482`) becomes a frozen instant and its Eastern date.
- [ ] Run: `python3 -m pytest tests/gcp/test_evening_windows.py tests/gcp/test_fetch_av_historical_options.py -q` (expect all pass). The render step and the baseline step (11).
- [ ] Commit: `fix(data): end the nightly option windows on the exchange's date`

## Task 5: Family D, the daytime fetchers

Spec: Design 1; Appendix A, family D; Problem ("The 31 are in scope because nothing but the schedule keeps them right"). Advances done_when[0], [6]. Needs: Tasks 1 and 2 (the adapter line of the retirement test).

**Files:** Modify, under `gcp/fetchers/`: `fetch_top_movers.py`, `fetch_premarket_refresh.py`, `fetch_economic_events.py`, `fetch_fred_rates.py`, `fetch_sec_filings.py`, `fetch_insider_transactions.py`, `backfill_daily_indicators.py`; and `tests/gcp/test_backfill_daily_indicators.py`. Create `tests/gcp/test_daytime_fetchers_market_date.py`.

What Appendix A leaves open: in `_filter_recent_rows` the function-local import keeps only `timedelta as _timedelta`. `_tickers_with_gaps` holds three `CURRENT_DATE`; the two `_earnings_calendar_tickers`, two each.

- [ ] Write `tests/gcp/test_daytime_fetchers_market_date.py`, every date test over the four instants:
  - `test_top_movers_snapshot_date`: `requests.get` answers one gainer; every row of `fetch_top_movers("k")` has `snapshot_date == E`.
  - `test_premarket_refresh_default_target`: `main()` with no arguments, `ALPHA_VANTAGE_API_KEY=k`, `mod.resolve_universe` recording and returning `[]`: its first argument is `E`.
  - `test_fred_release_window`: `FRED_API_KEY=k`, `requests.get` recording `params` and answering `{"release_dates": []}`: `realtime_start == E.isoformat()`, `realtime_end == (E + 90 days).isoformat()`.
  - `test_fred_rates_default_range`: `main()` with no arguments, `FRED_API_KEY=k`, `mod.is_cloud_sql_configured` true, `mod.fetch_dgs3mo` recording and returning an empty frame, `mod.upsert_daily_rates` returning 0: `start` and `end` are `(E - 14 days).isoformat()` and `E.isoformat()`.
  - `test_sec_filings_since`: `main()` with `--tickers SPY --since-days 3`, `mod.load_ticker_to_cik` returning `{"SPY": "1"}`, `mod.fetch_submissions` returning one row, `mod.filter_and_normalize` recording and returning an empty frame: its third argument is `E - 3 days`.
  - `test_insider_future_cutoff`, frozen with `pandas=True`: `mod.requests.get` answers transactions dated `E + 7 days` and `E + 8 days`; `fetch_for_ticker("SPY", "k")` returns the first only.
  - `test_recent_rows_cutoff`, frozen with `stdlib=True`: `_filter_recent_rows(rows, 7)` keeps a row dated `E - 7 days` and drops `E - 8 days`.
  - `test_the_three_statements_read_the_exchange_date`: each SQL function, its `query_to_dataframe` recording, issues a statement holding `market_today_sql()` (two, two and three times), no `CURRENT_DATE`, and bind names `{"w"}`, `{"w"}`, `{"d"}` (Review Focus).
- [ ] Run the three runs of "Red then green". Expect on the unmodified tree with `MARKET_CLOCK_HOST=utc`: the two evening instants of each date test fail by one day, the other two pass; the SQL test fails on `CURRENT_DATE`.
- [ ] Implement Appendix A, family D.
- [ ] In `tests/gcp/test_backfill_daily_indicators.py`, `assert 'CURRENT_DATE' in sql` (`:50`) and `assert 'm.date < CURRENT_DATE' in sql` (`:82`) assert the helper's text instead (both failed in the planning run); `today = date.today()` (`:266`, `:281`) becomes `market_today()`.
- [ ] Run: `python3 -m pytest tests/gcp/test_daytime_fetchers_market_date.py tests/gcp/test_backfill_daily_indicators.py tests/gcp/test_ew_fetcher_reader_retirement.py tests/gcp/test_sec_filings_retry.py tests/gcp/test_fetch_top_movers_intraday.py -q` (expect all pass). The render step and the baseline step (10).
- [ ] Commit: `fix(data): read the exchange's date in the daytime fetchers`

## Task 6: Family E, the signal monitor, the trade log and the weekend review

Spec: Design 1; Appendix A, family E; Decision 5 (the signal-monitor sites that stay). Advances done_when[0], [6]. Needs: Task 1.

**Files:** Modify `gcp/signal_monitor.py` (`fetch_latest_bar` and the import line only), `gcp/trade_logger.py`, `gcp/weekend_review.py`, `tests/gcp/test_trade_logger_reads.py`. Create `tests/gcp/test_signal_monitor_trade_log_market_date.py`.

What Appendix A leaves open: `log_trade` writes `str(market_today())`; `generate_weekly_review` writes `market_today().strftime('%Y-%m-%d')`.

- [ ] Write `tests/gcp/test_signal_monitor_trade_log_market_date.py`, over the four instants:
  - `test_fetch_latest_bar_keeps_the_exchange_days_bars`: a monitor built as `tests/gcp/test_signal_monitor.py::_build_monitor` builds one (build it first, then freeze `gcp.signal_monitor`), `requests.get` answering two 1-minute bars stamped `E 15:59:00` and `E + 1 day 09:30:00`: the returned frame has one row, dated `E`.
  - `test_the_trade_log_names_todays_file_and_date`: `TradeLogger(output_dir=tmp_path)._daily_file().name == f"{E}.parquet"`; with Cloud SQL off, `log_trade` of a row with no `trade_date` writes that file with `trade_date == str(E)`.
  - `test_the_trade_readers_default_to_the_exchange_date`: with Cloud SQL on and `gcp.database.query_to_dataframe_strict` recording, `get_daily_trades()` binds `d == str(E)` and `get_weekly_trades()` binds `end == str(E)`, `start == str(E - 6 days)`; with Cloud SQL off, `get_weekly_trades()` reads the seven files ending at `E`.
  - `test_week_ending_is_the_exchange_date`: `generate_weekly_review(trades_dir=str(tmp_path))` with `TradeLogger.get_weekly_trades` returning an empty frame gives `week_ending == E.isoformat()` (Review Focus).
- [ ] Run the three runs of "Red then green". Expect on the unmodified tree with `MARKET_CLOCK_HOST=utc`: the two evening instants fail by one day (the bar test keeps the other bar), the other two pass.
- [ ] Implement Appendix A, family E.
- [ ] In `tests/gcp/test_trade_logger_reads.py`, `date.today()` (`:220`, `:299`) becomes `market_today()`: `log_trade` appends to the exchange's day now.
- [ ] Run: `python3 -m pytest tests/gcp/test_signal_monitor_trade_log_market_date.py tests/gcp/test_trade_logger_reads.py tests/gcp/test_signal_monitor.py tests/gcp/test_signal_monitor_timezone.py tests/gcp/test_signal_monitor_persist.py -q` (expect all pass). The render step and the baseline step (7).
- [ ] Commit: `fix(data): read the exchange's date in the monitor and the trade log`

## Task 7: Family F, jobs with no scheduler or one outside the evening

Spec: Design 1; Design 2 (the scripts with a module-level `sys.path` line); Appendix A, family F except its last row. Advances done_when[0], [6]. Needs: Task 1.

**Files:** Modify `gcp/backtest_job.py`, `gcp/audit_job_runner.py`, `gcp/indicator_correlation_job.py`, `gcp/regime_combo_job.py`, `scripts/calibrate_thresholds.py`, `scripts/run_param_sweep.py`, `tests/integration/test_param_sweep_persistence.py`, `tests/scripts/test_calibrate_thresholds.py`. Create `tests/gcp/test_unscheduled_jobs_market_date.py`, `tests/scripts/test_unscheduled_scripts_market_date.py`.

What Appendix A leaves open: `apply_winner`'s statement is a plain string today; it becomes an f-string (it holds no brace and no `%`; checked). `gcp/audit_job_runner.py` has no `sys.path` line and runs as `python -m gcp.audit_job_runner`; its import is at module level like the rest.

- [ ] Write `tests/gcp/test_unscheduled_jobs_market_date.py`, over the four instants:
  - `test_backtest_window_ends_on_the_exchange_date`: with `BACKTEST_START` and `BACKTEST_END` unset, `_resolve_window() == ((E - 1825 days).isoformat(), E.isoformat())`.
  - `test_audit_runner_window`, frozen with `allow_instants=("datetime.now().timestamp()",)` (the id at `:116` stays): `AUDIT_SCRIPT_MODULE=x`, `AUDIT_WINDOW_DAYS=30`, `mod.subprocess.run` recording and returning an object with `returncode` 0: `main()` returns 0 and the recorded `argv` holds `--start`, `(E - 30 days).isoformat()`, `--end`, `E.isoformat()` in that order.
  - `test_correlation_and_regime_default_as_of`: `indicator_correlation_job.main([])` and `regime_combo_job.main([])`, their `*_AS_OF` variables unset, each module's `run` recording: the fourth positional argument is `E`.
- [ ] Write `tests/scripts/test_unscheduled_scripts_market_date.py`, over the four instants:
  - `test_calibrate_defaults`: `fetch_bars("SPY", 90, None)` with `mod.pd.read_sql` recording and returning an empty frame binds `cutoff == E - 90 days` and `end_excl == E + 1 day`; `calibrate_ticker` with no `as_of`, on bars built as `tests/scripts/test_calibrate_thresholds.py` builds them, returns `calibration_date == E`; `_parse_as_of(E.isoformat())` returns `E`, and the text of `E + 1 day` raises `SystemExit` naming "in the future".
  - `test_param_sweep_default_start`: `main()` with `--tickers SPY` and no `--start`, `mod.sweep_ticker` recording; `main` ends in `SystemExit`. Its second argument is `(E - DEFAULT_SWEEP_LOOKBACK_DAYS days).isoformat()`.
  - `test_apply_winner_writes_the_exchange_date` (one instant): with `gcp.database.execute_sql` recording, the statement holds `market_today_sql()` once, no `CURRENT_DATE`, and the bind names the unmodified code gives (record them first; Review Focus).
- [ ] Run the three runs of "Red then green". Expect, as in Task 5, the two evening instants to fail by one day on the unmodified tree with `MARKET_CLOCK_HOST=utc`.
- [ ] Implement.
- [ ] `tests/integration/test_param_sweep_persistence.py:121` compares `calibration_date = CURRENT_DATE`: it becomes the helper's text (run `make test-integration` if a Postgres is available, else say on the PR it was not run). In `tests/scripts/test_calibrate_thresholds.py`, each of its five `date.today()` reads that feeds a changed default becomes `market_today()`.
- [ ] Run: `python3 -m pytest tests/gcp/test_unscheduled_jobs_market_date.py tests/scripts/test_unscheduled_scripts_market_date.py tests/scripts/test_calibrate_thresholds.py -q`, and the existing test files that name the four `gcp` jobs (`grep -l` their module names under `tests/`). Expect all pass. The render step and the baseline step (9).
- [ ] Commit: `fix(data): read the exchange's date in the on-demand jobs`

## Task 8: Family G, the API routes and `strat_pred_serve`

Spec: Design 1 (the dead-branch row); Appendix A, family G; Problem row 8; AGENTS.md "Browser proof" (the API test of the changed response). Advances done_when[0], [4] (first sentence), [6]. Needs: Task 1.

**Files:** Modify `platform/api/main.py`, `platform/api/routers/catalysts.py`, `platform/api/routers/dashboard.py`, `platform/api/routers/grid.py`, `gcp/research/strat_engine/strat_pred_serve.py`, `tests/api/test_grid_router.py`. Create `tests/api/test_evening_dates.py`.

What Appendix A leaves open:
- `platform/api/main.py` and `dashboard.py` already import `market_today`; `catalysts.py` and `grid.py` gain the import.
- `get_catalyst_snapshot`: `_date.fromisoformat(as_of) if as_of else market_today()`.
- `predict_one`: `since=(market_today() - pd.Timedelta(days=30)).isoformat()` (a `date` minus a `pd.Timedelta` is a `date`; run).
- The instant in `get_grid_timeseries` (`datetime.now(timezone.utc)`) stays.

- [ ] Write `tests/api/test_evening_dates.py`. Apps are built per router as `tests/api/test_grid_router.py` and `tests/api/test_strat_engine_predict.py` build theirs; every request goes through `TestClient`. The evening instant is `2026-11-14T01:30:00Z` (Friday 2026-11-13 20:30 EST); every test also runs at the other three of the four instants.
  - `test_catalyst_events_default_window`: `GET /api/catalysts/events` with no dates, `_load_cached_events` returning `{"events": []}`, `_fetch_live_events` returning `[]`, `_db_catalyst_events` recording and returning `[]`: its first two arguments and the response's `date_range` are `2026-11-10` and `2026-11-27` in the evening, `E - 3 days` and `E + 14 days` as ten-character text elsewhere (Review Focus).
  - `test_catalysts_for_ticker_window`: `GET /api/catalysts/ticker/SPY`, the cache stubbed the same way, `_fetch_live_events` recording: its window and the response's `date_range` are `E - 7 days` to `E + 30 days` (`2026-11-06` to `2026-12-13` in the evening).
  - `test_catalyst_snapshot_cutoff`, frozen with `stdlib=True` (the unmodified handler imports `date` inside itself): `GET /api/catalysts/asof/SPY` with no `as_of`, `gcp.database.query_to_dataframe` recording and returning empty frames: every bound `cutoff` is `2026-11-13` and every `start` `2026-11-06` in the evening. With `as_of=2026-11-01` the cutoff is that date at every instant (Review Focus).
  - `test_grid_timeseries_default_expiration`: `GET /api/options/SPY/grid/timeseries` with no `expiration`, the query returning realtime rows for expirations `2026-11-13` and `2026-11-20`: the response's `expiration` is `2026-11-13` in the evening, and `2026-11-20` at `2026-11-14T05:30:00Z` (Saturday 00:30 EST).
  - `test_live_chain_floor`: `GET /api/options/SPY/grid`, `gcp.database.query_to_dataframe` recording and returning empty frames: every bound `floor` is `"2026-10-24"` in the evening, `str(E - 20 days)` elsewhere. `grid._load_chain_for_live("SPY", today=date(2026, 1, 5))` binds `"2025-12-16"` at every instant (Review Focus).
  - `test_reference_levels_recency`: `GET /api/market/reference/SPY/2026-10-15` on the app of `platform/api/main.py`, reached as `tests/api/test_platform_api.py` reaches it, `_CLOUD_SQL` true and `_daily_reference_query` returning one row dated `2026-10-09`: `stale_days == 6` in the evening (29 days back is recent) and at `DAYTIME`. For the summer instants request the date 29 days before `E`, with a row 6 days before that.
  - `test_predict_one_feature_window`, frozen with `pandas=True`: `POST /api/admin/strat-engine/predict`, signed in and with the model load stubbed as `test_strat_engine_predict.py` does, `load_strat_features_with_levels` recording `since` and raising a marker exception the test expects: `since == "2026-10-14"` in the evening, `(E - 30 days).isoformat()` elsewhere. If the route cannot reach `predict_one` without a model artifact, call `predict_one(None, "IWM", "15m")` directly for this case and say so on the PR.
  - `test_live_overlay_replaces_todays_row`: `asyncio.run(dashboard._apply_live_overlay("SPY", {}))` with `dashboard._query_fn` returning 30 daily rows whose newest is dated `E`, `dashboard.get_live_quote` an async stub returning `{"price": 500.0}`, `dashboard.ET_TZ` set to `None`, and `lib.indicators.calculate_rsi` wrapped to record the series length: 30, not 31.
- [ ] Run the three runs of "Red then green". Expect on the unmodified tree with `MARKET_CLOCK_HOST=utc`, evening instant: the events window `2026-11-11` to `2026-11-28`, the cutoff `2026-11-14`, the expiration `2026-11-20`, the floor `2026-10-25`, `stale_days` 0, `since` `2026-10-15`, the overlay 31. These follow from the rule and were not run for this plan; this run is their first evidence.
- [ ] Implement.
- [ ] `tests/api/test_grid_router.py:160` and `:1101` read `date.today()`: change to `market_today()`.
- [ ] Run: `python3 -m pytest tests/api -q` (expect no failure `origin/main` does not have; `test_openapi_snapshot.py` passes because no route or response model changed) and `git status --short platform/api/openapi.json` (expect empty).
- [ ] The render step (this task moves most of the 44 cited lines) and the baseline step (8).
- [ ] Commit: `fix(api): count default windows from the exchange's date`

## Task 9: Family H, the Discord date argument

Spec: Design 1 (the optional-argument row); Appendix A, family H; Problem row 7; Design 4 (last row of the table). Advances done_when[0], [4] (second sentence), [6]. Needs: Task 1.

**Files:** Modify `gcp/discord_interactions/main.py` (the import goes at module level below the `sys.path` line; the function-local import of `replay_probe_window` is not moved). Create `tests/gcp/test_discord_date_arg_evening.py`.

- [ ] Write `tests/gcp/test_discord_date_arg_evening.py` (`import gcp.discord_interactions.main as di`):
  - `test_relative_dates_resolve_to_the_exchange_day`: at `2026-11-14T01:00:00Z` (Friday 20:00 EST), `parse_date_arg("today") == date(2026, 11, 13)`, `parse_date_arg("-1") == date(2026, 11, 12)`, `parse_date_arg("2026-11-13")` is that date, and `parse_date_arg("2026-11-14")` raises `ValueError` matching `in the future`.
  - `test_the_other_instants`: at `DAYTIME` and the two summer instants, `today` is `E`, `-1` is `E - 1 day`, and the text of `E + 1 day` is refused.
  - `test_a_passed_today_is_used` (Review Focus): at the evening instant, `parse_date_arg("today", today=date(2026, 1, 5)) == date(2026, 1, 5)`.
- [ ] Run the three runs of "Red then green". Expect on the unmodified tree with `MARKET_CLOCK_HOST=utc`, evening instant: `today` gives `2026-11-14`, `-1` gives `2026-11-13`, and `2026-11-14` is accepted (the spec's Design 4 table).
- [ ] Implement Appendix A, family H.
- [ ] Run: `python3 -m pytest tests/gcp/test_discord_date_arg_evening.py tests/gcp/test_discord_interactions.py -q` (expect all pass). The render step and the baseline step (1).
- [ ] Commit: `fix(discord): resolve relative dates on the exchange's clock`

## Task 10: Family I, the library defaults

Spec: Design 1 (the optional-argument row and the thrown-away-date row); Appendix A, family I. Advances done_when[0], [4] (third sentence), [6]. Needs: Task 1.

**Files:** Modify `lib/agents/summarizers.py`, `lib/data_loader.py`, `lib/strategies/calibration.py`, `lib/strategies/exit_config_overrides.py`, `lib/indicators.py`, `lib/trading_analysis.py`, `tests/lib/test_strategies_calibration.py`, `tests/lib/test_exit_config_overrides.py`. Create `tests/lib/test_library_today_defaults.py`.

What Appendix A leaves open: the two ORB functions write `datetime.combine(datetime(2000, 1, 1), market_open)` and gain no import; the rest of each expression is unchanged.

- [ ] Write `tests/lib/test_library_today_defaults.py`. The evening instant is `2026-11-14T01:30:00Z`; 2026-11-13 is a Friday. Each date test also runs at `DAYTIME` as written, and at the two summer instants with its dates shifted to that Friday.
  - `test_chain_freshness_counts_from_the_exchange_date`: in the evening `_check_chain_freshness(date(2026, 11, 11))` gives no finding (2 trading days; `MAX_OPTIONS_STALE_TRADING_DAYS` is 2) and `date(2026, 11, 10)` a message naming `2026-11-13`. At `DAYTIME`, `date(2026, 11, 10)` gives none and `date(2026, 11, 9)` a message naming `2026-11-12`. With `target_date=date(2026, 11, 20)` the message names that date at every instant (Review Focus).
  - `test_gamma_levels_freshness_tier`: `summarize_gamma_levels("SPY")`, its query stubbed as `tests/agents/test_agent_summarizers.py` stubs `_query`, no realtime rows and an EOD chain dated two trading days before `E` (`2026-11-11` in the evening): the result's `data_source` is `classify_gamma_freshness(2)`. Assert first that `classify_gamma_freshness(3)`, which the host date gives in the evening, is a different value.
  - `test_staleness_age`: in the evening `_check_staleness(df, "SPY", max_age_days=1, on_stale="error")` does not raise for a frame whose newest date is `2026-11-12` and raises for `2026-11-11`. With `today=date(2026, 12, 1)` it raises for both (Review Focus).
  - `test_calibration_age`, `test_override_age`: `cache_clear()` before and after; the database stubbed as `tests/lib/test_strategies_calibration.py` and `tests/lib/test_exit_config_overrides.py` stub it, returning one row dated 180 days before `E`: `_latest_calibration("SPY")` and `_latest_overrides("SPY")` return the row (`_STALE_DAYS` is 180; from the host date it is 181 days and stale).
  - `test_orb_end_time_does_not_depend_on_the_day`: `calculate_orb` and `MarketAnalyzer._calculate_orb` on the same small frame return equal frames at `2026-11-14T01:30:00Z` and at `2026-07-10T15:00:00Z`; frozen with `stdlib=True` over `lib.indicators` and `lib.trading_analysis`, neither raises (the second imports `datetime` inside itself).
- [ ] Run the three runs of "Red then green". Expect on the unmodified tree with `MARKET_CLOCK_HOST=utc`, evening instant: each count is one more (the chain of `2026-11-11` reads stale, the gamma tier is the staler one, the frame of `2026-11-12` raises, both rows read stale); the ORB test passes in this mode and fails with `HostClockRead` by default.
- [ ] Implement Appendix A, family I.
- [ ] In `tests/lib/test_strategies_calibration.py`, the two `patch.object(calibration, "date")` stubs (`:349`, `:361`) become freezes at `2026-11-11T16:00:00Z` and `2026-07-02T16:00:00Z`. Its other `date.today()` reads, and the one at `tests/lib/test_exit_config_overrides.py:58`, become `market_today()` where they feed the two functions.
- [ ] Run: `python3 -m pytest tests/lib tests/agents -q` (expect no failure `origin/main` does not have). `tests/lib/test_signals_per_ticker_overrides.py`, `tests/lib/test_data_loader.py:600` and `tests/agents/test_agent_summarizers.py` read the host date near these functions: change the reads that feed a changed default. The render step and the baseline step (7).
- [ ] Commit: `fix(lib): default today to the exchange's date in the library`

## Task 11: The run-hours test and the stage-one lists

Spec: Design 3 ("Why 'no value changes' is proven and not argued"); Design 5; Appendix A (the "Wrong today?" column); Appendix B. Advances done_when[0], [5] (second sentence). Needs: Tasks 2 to 10.

**Files:** Create `tests/meta/test_stage_one_run_hours.py`, `tests/meta/test_market_date_stage_one.py`.

**Interfaces:** Consumes, unedited, `scripts.maintenance.doc_inventory.deploy_jobs(root)`, `deploy_schedulers(root)`, `_overrides_argv(args)`, and `tests.meta.test_timezone_boundaries` (`BASELINE`, `_scan`). Produces:
- in `test_stage_one_run_hours.py`: `EVENING_HOURS = range(19, 24)`; `NO_JOBS`, written out (below); `start_hours(cron: str) -> set[int]`, the hours the hour field of a five-field cron can start a run in (lists, ranges, steps, `*`); `resolved_args(entry: dict, jobs: dict) -> list[str]`: when `_overrides_argv(entry["args"])`, the entry's own tokens that are not `NAME=value` env pairs, else the `args` of its job, split on spaces (an entry that overrides only an env var, as `backfill-indicators-weekly` does, keeps the job's arguments); `evening_entries(root: Path) -> list[tuple[str, str, list[str]]]`: `(name, cron, resolved_args)` for each scheduler entry whose `target_job` is in `NO_JOBS` and whose `start_hours` meets `EVENING_HOURS`.
- in `test_market_date_stage_one.py`: `STAGE_ONE` and `STAYS`, each `dict[file, dict[rule, list[identity]]]`, written out; `TESTS_THAT_READ_THE_EXCHANGE_DATE: tuple[str, ...]`, the existing test files Tasks 2 to 10 edited.

`NO_JOBS` is the 15 scheduled jobs all of whose Appendix A sites are marked "no": `audit-brief-bias`, `audit-walkforward`, `build-realtime-gex`, `backfill-daily-indicators`, `fetch-economic-events`, `fetch-fred-rates`, `fetch-insider-transactions`, `fetch-premarket-refresh`, `fetch-sec-filings`, `fetch-top-movers`, `refresh-earnings-views`, `regime-combo`, `signal-monitor`, `weekend-review`, `calibrate-thresholds`. `fetch-av-options-backfill` is not one: its `main` has a "yes" site.

Prototyped on 161fa992 through the repo's reader: 67 jobs, 65 scheduler entries; the 15 jobs have 20 entries; exactly one starts in the evening hours, `("refresh-earnings-views-weekly", "0 20 * * 0", ["--mode=weekly"])`.

- [ ] Write `tests/meta/test_stage_one_run_hours.py`:
  - `test_no_job_whose_sites_are_right_by_schedule_runs_in_the_evening`: every job of `NO_JOBS` is in `deploy_jobs()` and has a scheduler entry (a renamed job cannot pass empty); `evening_entries(REPO) == [("refresh-earnings-views-weekly", "0 20 * * 0", ["--mode=weekly"])]`.
  - `test_the_weekly_views_run_never_reaches_the_daily_sites`: `gcp.refresh_earnings_views.main(["--mode=weekly"])`, `is_cloud_sql_configured` true and `refresh_weekly` and `refresh_daily` recording, calls the first once and the second never. By `ast` on the file: the module-level functions reachable from `refresh_weekly` by bare-name calls hold no call of `market_today` or `market_today_sql`, and `refresh_daily` holds both (so the check cannot pass empty).
  - `test_a_moved_schedule_or_a_changed_mode_fails`, on a copy of `gcp/deploy.sh` under `tmp_path / "gcp"`: (a) `"realtime-gex-daily" "0 17 * * 1-5"` rewritten to `"0 21 * * 1-5"` puts `realtime-gex-daily` in `evening_entries(tmp_path)`; (b) the job's two `--args="--mode=weekly"` rewritten to `--mode=daily` make the weekly entry's resolved arguments `["--mode=daily"]`; (c) the weekly entry rewritten to `_schedule_args "refresh-earnings-views-weekly" "0 20 * * 0" "refresh-earnings-views" "--mode=daily"` does the same. Each asserts the text was found before it was replaced.
  - `test_start_hours`: `"30 9-15 * * 1-5"` gives 9 to 15; `"0 7,10,13,17 * * 1-5"` those four; `"0 */6 * * *"` gives `{0, 6, 12, 18}`; `"15 * * * *"` all 24.
- [ ] Write `tests/meta/test_market_date_stage_one.py`:
  - `STAGE_ONE` and `STAYS` are derived once, on the merge base, then written out in the file: for each row of Appendix A (and B), the identity is the third element of the `_scan(path)` hit with that rule at that line. Check values: `STAGE_ONE` holds 71 identities in 39 files, 64 `host-today` and 7 `sql-utc-date`; `STAYS` holds 31 in 12 files; one identity is in both, once each (`scripts/fetch_earnings_calendar.py`, `host-today`, `EarningsCalendarFetcher.fetch_unusual_whales_earnings::datetime.now()`). The SQL identities are `_query_watchlist::fstr#3c17358f2881`, `_tickers_with_gaps::fstr#b950f2df4227`, `_earnings_calendar_tickers::fstr#266f9c5482ea` (history), `_earnings_calendar_tickers::fstr#591204bc497c` (one text, in `fetch_insider_transactions.py` and in `fetch_sec_filings.py`), `refresh_daily::fstr#e2ebe6247dcf`, `apply_winner::str#f9f26d5f0493`.
  - `test_the_lists_are_the_spec_s`: those counts.
  - `test_the_baseline_of_the_39_files_is_exactly_the_31`: for every file of `STAGE_ONE` and every rule, the baseline's entries equal `STAYS`'s as multisets (`Counter`). The message lists what is left over and what is missing. This is "none of the 71 is in the baseline and each of the 31 still is", and it fails if an entry is added to one of the 39 files.
  - `test_the_edited_tests_do_not_read_the_host_clock` (Review Focus): for each file of `TESTS_THAT_READ_THE_EXCHANGE_DATE`, `_scan(path)` holds no `host-today` hit.
- [ ] Run: `python3 -m pytest tests/meta/test_stage_one_run_hours.py tests/meta/test_market_date_stage_one.py -q` (expect all pass: Tasks 2 to 10 took the 71 out of the baseline). A file of the list that still has a host read fails the last test; a stamp such as `datetime.now().isoformat()` in a fixture row becomes `lib.eastern_time.utc_now().isoformat()`. Fix the test file, not the list.
- [ ] Records. For [0]: in a scratch edit point `BASELINE` at the merge base's file (`git show "$(git merge-base HEAD origin/main)":tests/fixtures/timezone_boundary_baseline.json > /tmp/old-baseline.json`); expect the baseline test to fail listing 71 leftovers; revert. For [5]: remove `refresh-earnings-views-weekly` from the expected list in a scratch edit; expect the first run-hours test to fail naming it; revert.
- [ ] Commit: `test(data): pin the stage-one sites and the hours their jobs run`

## Task 12: The whole baseline diff, the opt-out count and the whole suite

Spec: Design 5; Done when ([0], [6] second sentence, [7] first clause). Advances done_when[0], [6], [7]. Needs: Tasks 1 to 11. A check task: it commits only what a check makes it fix.

- [ ] Check [0] by identity:

  ```bash
  python3 - <<'EOF'
  import json, subprocess
  from collections import Counter
  from tests.meta.test_market_date_stage_one import STAGE_ONE
  path = "tests/fixtures/timezone_boundary_baseline.json"
  base = subprocess.run(["git", "merge-base", "HEAD", "origin/main"], capture_output=True, text=True, check=True).stdout.strip()
  old = json.loads(subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True, check=True).stdout)
  new = json.load(open(path))
  flat = lambda d: Counter((f, r, i) for f in d for r in d[f] for i in d[f][r])
  gone, added = flat(old) - flat(new), flat(new) - flat(old)
  print(sum(gone.values()), sum(added.values()), gone == flat(STAGE_ONE))
  EOF
  ```

  Expect `71 0 True`. Paste it on the PR.
- [ ] Run: `python3 -m pytest tests/meta -q` (expect all pass) and `git diff --stat origin/main -- tests/meta/test_timezone_boundaries.py lib/eastern_time.py gcp/deploy.sh` (expect empty).
- [ ] Check the opt-outs: `diff <(git grep -c 'tz-ok:' "$(git merge-base HEAD origin/main)" -- gcp lib scripts platform/api | cut -d: -f2-) <(git grep -c 'tz-ok:' HEAD -- gcp lib scripts platform/api | cut -d: -f2-)` prints nothing (26 lines in 10 files on 161fa992).
- [ ] Review Focus, the hour a test runs at. Run the nine family test files and every file of `TESTS_THAT_READ_THE_EXCHANGE_DATE` with the host's date ahead of the exchange's: `TZ=Pacific/Kiritimati python3 -m pytest <those files> -q`. Expect the same result as without `TZ`. (Executed for this plan: under that zone `date.today()` was 2026-11-15 while the Eastern date was 2026-11-14. The two agree only from 05:00 to 10:00 UTC; do not run it then.) A test that fails only under the zone still takes its expectation from the host: fix it and add its file to the list.
- [ ] Run: `make test` (expect no failure that `origin/main` does not have). Then the render step once more; `git status` shows no change to the three docs, or commit `docs(infra): re-render the inventory for the stage-one dates`.
- [ ] Write the list for the PR body: every existing test whose expectation or clock stub changed, one line each with the reason. From this plan: the adapter entry in `tests/fixtures/earnings_calendar_sources.py` (11 tests read the changed SQL through it); `test_ew_fetcher_reader_retirement.py:62`; `test_backfill_daily_indicators.py:50` and `:82`; the four stubs of `test_earnings_long_watchlist_freshness.py`; the two of `test_strategies_calibration.py`; the two integration tests; and each host-date read replaced in Tasks 3 to 10. `git diff --stat origin/main -- tests` is the check that none is missing.

## Task 13: Product record, site notes, the measured query and the gate

Spec: Design 4 (last paragraph); Design 7; Capacity; Done when ([7], [8]); product-delivery Phase 4 and Phase 5. Closes done_when[7], [8]. Needs: Tasks 1 to 12. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/`, `tests/` or `platform/api` may change without redoing all four of them.

- [ ] Measure one changed query in both spellings, read-only: the statement of `_tickers_with_gaps`, the one of the seven on another table than the spec's Design 4 measured. Print it: `python3 -c "from unittest.mock import patch; import pandas as pd; import gcp.fetchers.backfill_daily_indicators as m; q = patch.object(m, 'query_to_dataframe', return_value=pd.DataFrame()).start(); m._tickers_with_gaps(7); print('EXPLAIN (ANALYZE, BUFFERS) ' + q.call_args[0][0].replace('(:d ||', '(7 ||'))" > /tmp/gaps_market.sql` (the bind is replaced with its opening text: a bare `:d` also matches inside `::date`). Make `/tmp/gaps_current.sql` by replacing the helper's text with `CURRENT_DATE`. Run `./scripts/db_query_cr.sh -f` on each, with no `--commit`. Keep both plans and both execution ids. Expect the same scan node on `market_data_daily` and the same `rows=` on it. If they differ, stop and tell the owner. If the session cannot reach GCP, ask the owner to run the two commands. [7] is not ticked without them.
- [ ] Push with `git push -u origin fix/feat-data-001-deployed-dates-exchange-clock` and open a **draft** PR. Title: `FEAT-DATA-001: deployed code takes today from the exchange's clock`. Body, on the repository's template: the spec path and this plan's path; the nine done_when items, each as a `- [ ]` line that starts with the item's text; the four Capacity labels filled from the spec's Capacity section, said to be the spec's measurements of 2026-10-18 and 2026-10-25 and not new ones, with its note that `compute-earnings-reactions` is over the quarter REQ-CAP-001 allows and is not fixed here; the list of Task 12; the two query plans with their execution ids; the `71 0 True` line; the red-then-green records of Tasks 2 to 10; the choices listed in Global Constraints; that nothing changes in production at the merge except the API, which `deploy-staging.yml` deploys from `main`; that `platform/api/openapi.json` is unchanged and the API test of the changed responses is `tests/api/test_evening_dates.py`.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-DATA-001` record only (`:513` on 161fa992; not the table row): in the Status cell (`:520`) append, before the closing ` |`: `; 71 sites in 39 files of deployed code take today from lib.eastern_time (market_today, market_today_sql) where they read the container's UTC date or CURRENT_DATE, stage 1 of the market-time sweep ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed; no stored row is rewritten)`. Last reviewed (`:524`) becomes the date of the PR's head commit; set it again if a later commit lands on another day.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, section `### FEAT-DATA-001` (`:320`): append to its `**PR lineage:**` line (`:346`) ` · [#N](https://github.com/TeneikaAskew/stocks/pull/N) *remediation: deployed dates on the exchange's clock, stage 1, spec [#1932](https://github.com/TeneikaAskew/stocks/pull/1932) approved in [#1938](https://github.com/TeneikaAskew/stocks/pull/1938)*`. Commit both docs and the plan: `docs(product): record the stage-one date sweep under FEAT-DATA-001`.
- [ ] Site notes, step 1 (preflight). With every code and test commit in place and a clean tree, run `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`. It prints a verdict and installs nothing yet. Copy its `source_identity_sha256`.
- [ ] Site notes, step 2. In `docs/product/03-SITE-TRACEABILITY.md`, table `## Implementation-source notes` (`:1297`), write six rows `| FEAT-DATA-001 | <component> | source_identity_sha256=<that hash>; <text> |` and change no other byte. On 161fa992 the table holds a FEAT-DATA-001 row for DASHBOARD-01 and none for the other five. Order among the FEAT-DATA-001 rows: ADMIN-02, **ADMIN-08**, CHARTS-01, **DASHBOARD-01**, **DASHBOARD-03**, DASHBOARD-04, **DASHBOARD-06**, **DASHBOARD-21**, JOURNAL-01, LIVE-03, LIVE-08, **OPTIONS-01**, SHARED-07. Each text is the component's opening clause, one space, then the shared sentences, with the files of the row's bracket in place of `<test>` (the bracket itself is not written):

  ```text
  ADMIN-08      `POST /api/admin/strat-engine/predict`: `predict_one` (`gcp/research/strat_engine/strat_pred_serve.py`) starts its 30-day feature window from   [tests: tests/api/test_evening_dates.py]
  DASHBOARD-01  Job `fetch-earnings-history` (`gcp/fetchers/fetch_earnings_history.py`): its Sunday weekly scope and the window of `_earnings_calendar_tickers` are taken from   [tests: tests/gcp/test_earnings_scope_evening.py]
  DASHBOARD-03  `GET /api/market/reference/{ticker}/{date}`: `get_reference_levels` judges whether a request is under 30 days old from   [tests: tests/api/test_evening_dates.py]
  DASHBOARD-06  `GET /api/catalysts/events`, `/api/catalysts/ticker/{ticker}` and `/api/catalysts/asof/{ticker}` take their default window and cutoff, and job `fetch-earnings-calendar` (`scripts/fetch_earnings_calendar.py`) takes its scope, its windows and its options-enrichment targets, from   [tests: tests/api/test_evening_dates.py, tests/scripts/test_fetch_earnings_calendar_evening.py]
  DASHBOARD-21  Job `fetch-av-options-backfill` (`gcp/fetchers/fetch_av_historical_options.py`) ends its `--from-latest` range on   [tests: tests/gcp/test_evening_windows.py]
  OPTIONS-01    `GET /api/options/{ticker}/grid` (the 20-day floor and `days_behind` of `_load_chain_for_live`) and `GET /api/options/{ticker}/grid/timeseries` (the default expiration) count from   [tests: tests/api/test_evening_dates.py]

  shared        `lib.eastern_time.market_today()`, the exchange's date (in SQL, the text of `market_today_sql()`), where the source read the container's UTC date, which is the next day from 19:00 Eastern in winter and 20:00 in summer until midnight Eastern. Outside those hours the value is the same. No route, response shape or stored row changed. Tests: `<test>`, `tests/meta/test_market_date_stage_one.py`, `tests/meta/test_stage_one_run_hours.py`. Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.
  ```

  The DASHBOARD-01 row exists: it becomes the new hash, this change's text, then ` Earlier: ` and that row's earlier prose unchanged (its text after the old hash and `; `). Do the same for any of the six another lane has added by then, and tell the owner.
  Commit: `docs(site): note the stage-one date sweep under six components`.
- [ ] Site notes, step 3. Run the same `produce` command again; it now writes the sidecar. Commit: `docs(site): regenerate the source snapshot`. These two commits are the last before the push.
- [ ] Site notes, step 4. Run `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0 and `implementation-source identity matched`). If `origin/main` moved, or review changes a watched file later: merge `origin/main`, run the render step and the baseline step, rerun Task 12's first check, then repeat steps 1 to 4 with the new hash in all six rows.
- [ ] Docs audit, branch against `main`: `python3 scripts/maintenance/docs_audit.py > /tmp/audit-branch.txt`; then `git worktree add --detach /tmp/audit-main origin/main`, the same command there into `/tmp/audit-main.txt`, and `git worktree remove /tmp/audit-main`. The branch reports no `[P1]`, `[P2]` or `[P3]` line that `main` does not. Exit code 2 means the run itself failed.
- [ ] Run on the final head: `make test`, `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` and `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0). Push.
- [ ] Put the final body on the PR, tick each done_when box with its evidence beside it (test name, command output, execution id, file), then mark the PR ready for review. Review follows CLAUDE.md 2.5: the first-review comments, zero unresolved threads, two rounds at most.

## Close-out (not tasks; the owner's steps)

The spec's Close-out, steps 1 to 6, is the list; it is not repeated here. None of it is done by the implementer of this plan, none is a done_when box, and the PR deploys nothing. What this plan adds to it:

- Step 4's query goes through `./scripts/db_query_cr.sh` with no `--commit`.
- Step 6 includes this plan's `status: done`, on a `docs/` branch after the merge (product-delivery Phase 5 step 7).
- AGENTS.md "Browser proof" makes runs against the deployed site the owner's close-out steps for a change a user can see. The spec's Design 7 says each note claims no change on a page, and its Close-out lists no such run. This plan adds none; the owner decides whether the evening default window of the catalysts list counts.
