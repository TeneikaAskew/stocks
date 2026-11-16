---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
branch: feature/feat-data-001-bar-misprint-flags
pr: null
status: ready
---

# Flags for the vendor's misprints in the 1-minute bars of SPY, QQQ and IWM: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] to [14]. The spec's body counts them differently ("`done_when` item 13" for the PR-body measurements, "item 14" for the integration test, "item 15" for the nightly, "item 17" for the manifest); this plan follows the frontmatter, and the map below says which is which.

**Goal:** A print that sits far outside its own minute is flagged, per bar and side, in two new tables that the nightly 21:00 ET fetch job fills for the previous and the current Eastern month, with a history run, a replace that clears what it invalidates under a shared lock, and counts in the bucket manifest. No bar is changed and no consumer reads a flag.

**Architecture:** A pure module, `lib/bar_prints.py`, measures every bar once (`print_geometry`) and applies the scale and the threshold (`isolated_prints`). A new writer of its own two tables, `gcp/fetchers/intraday_bar_flags.py`, runs each ticker-month in one transaction: configuration, advisory lock, one read, one write. `fetch_alphavantage_intraday.main()` calls it after the fetch loop and before the bars export; `--flag-bars-from` runs the history. `gcp.database.replace_rows_in_window` gains two keywords, `clear_span_tables` and `advisory_locks`, which `replace_month` passes to both of its swaps. `export_window` reads the coverage rows into each manifest entry.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy `text()` with pg8000 through `gcp.database`, argparse, pytest (`monkeypatch`, `caplog`), `threading` for the race test, Postgres 15 in CI for `tests/integration/`.

**Spec:** docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md (approved, PR #1988). On 2026-11-16, when this plan was written, the spec was on `origin/docs/spec-feat-data-001-bar-misprint-flags-r2` (503ec867) and not yet on `origin/main` (9f2df577); it was read from its branch. No code branch opens before it is on `main`.

## Order, and what the owner asked for first

Owner priority, 2026-11-16: on Monday's 08:30 ET brief the premarket highs of SPY, QQQ and IWM were set by isolated bad prints (IWM 278.92 against a consolidated 276.90), so every call trigger was wrong.

- **Tasks 1 to 7 come first**, in this order: the geometry and the rule (`lib/bar_prints.py`, Tasks 1 and 2), the labelled sessions that prove them (Task 3), the tables (Task 4), the pass (Tasks 5 and 6) and the nightly call (Task 7). After Task 7 the branch holds a working nightly flag pass. Tasks 8 to 12 are the history run, the replace, the lock on the replace's side, the race test and the manifest. Tasks 13 and 14 close.
- **This is still one branch and one PR** (the spec's Scope). "First" is commit order, so a reviewer can accept the rule and the nightly pass before reading the rest. Nothing runs in production until the PR merges and the owner runs Close-out steps 1 and 2.
- **Out of this spec's scope, and not in this plan: the brief's premarket high ignoring a flagged bar side.** The spec changes no consumer (Scope; Non-goals; decision 11; Design 10). That change belongs to the brief spec being drafted on `docs/spec-feat-playbook-001-brief-says-what-the-data-says`. No task here edits `gcp/premarket_brief.py`, `gcp/fetchers/fetch_market_data.py`, `lib/indicators.py` (the premarket print filter, `:661-713`) or any reader of the bars, so nothing is built twice.
- **What the brief spec can take from here.** `lib.bar_prints.print_geometry` and `isolated_prints` are pure and take any frame of 1-minute bars, so a consumer can call them over the morning's premarket bars. What it cannot take is the stored flag of the same morning: the pass that writes it runs at 21:00 ET, after the 08:30 brief, and a bar is judged only once two later bars exist (Design 1, "Judged"; Design 10, "Look-ahead"). The brief spec has to decide that; this plan only keeps the rule callable.

## Global Constraints

- Base: `origin/main` once it holds the r2 spec. The spec's code references are to `main` a34bbd40 and 4155a10f; `git diff --stat a34bbd40 9f2df577 -- gcp lib tests scripts` is empty (run 2026-11-16), so its line numbers hold on 9f2df577. Rerun that diff against the base actually used. Branch `feature/feat-data-001-bar-misprint-flags`. This plan is committed alone on `docs/plan-feat-data-001-bar-misprint-flags` and merged before the code branch opens.
- SPY, QQQ and IWM only. `FLAG_TICKERS = ("SPY", "QQQ", "IWM")`; any other ticker raises `ValueError` before a query.
- No bar is changed, deleted, replaced or interpolated, and no value is written in place of one (CLAUDE.md 3.7). The new module writes only `intraday_bar_flags` and `intraday_bar_flag_coverage`.
- No consumer reads the flags. No feature, level, signal, calibration, exit, brief, chart or route changes.
- Not in the PR's diff (done_when[12]): `lib/eastern_time.py`, `lib/indicators.py`, `lib/level_calibration.py`, `gcp/bar_recompute.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/deploy.sh`, `platform/api`, `CLAUDE.md`. Unmodified tests: `tests/meta/test_production_writers.py`, `tests/meta/test_timezone_boundaries.py`, `tests/fixtures/timezone_boundary_baseline.json`, `tests/gcp/test_av_intraday_universe.py`, `tests/gcp/test_intraday_writers_utc.py`, `tests/gcp/test_intraday_replace_levels_tables.py`.
- Exact values, copied from the spec: `RULE_VERSION = "isolated-print-v1"`; `PARAMS = {"neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0, "floor_bp": 50.0}`; threshold `max(6 x scale, 0.0050 x reference)`; flagged strictly beyond the bound; read margin 7 days on each side of `lib.eastern_time.intraday_month_window`; pass `lock_timeout` `120s`, replace `lock_timeout` `30s`; lock key, the first 8 bytes of sha256 of `intraday_bar_flags:<ticker>:1min:<YYYY-MM>` as a signed big-endian 64-bit integer; variable `INTRADAY_BAR_FLAGS` (`off`, any letter case); flags `--flag-bars-from YYYY-MM`, `--flag-bars-to YYYY-MM`; log lines starting `bar flags month:`, `bar flags:`, `bar flags failed (outage)`, `bar flags failed (defect)`, `BARS-CHANGED`, `REBUILD intraday_bar_flags`, `REBUILD intraday_bar_flag_coverage`; manifest key `flags`, with `{"state": "not_judged"}` for a month without a coverage row.
- The read, exact SQL: `SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`. It runs on the transaction's own connection, not through `query_to_dataframe_strict`. No `try` around a read or a write: nothing is caught inside `flag_months`.
- A month is a `(year, month)` tuple everywhere, as `export_intraday_bars.nightly_months` returns it.
- Time (CLAUDE.md 3.9): a zone changes only through `lib/eastern_time.py` (`market_date`, `market_today`, `session_schedule`, `intraday_month_window`). `tests/meta/test_timezone_boundaries.py` fails on a new hand-rolled conversion.
- Capacity (CLAUDE.md Rule 0; spec Design 13), each figure tied to a test or to Task 13's measurement: nightly, 27 round trips (3 coverage reads, and 4 statements for each of 6 ticker-months), under 60 s against the job's 3,600 s; committed history, 289 round trips for 72 months, at most 614 s, in two executions a ticker; one ticker-month in memory, at most 31,711 rows; no statement per bar or per flag; no new job and no new schedule.
- Production access from this branch is read-only and is only Task 3 (the fixture exports) and Task 13 (the EXPLAIN and the bucket read), each through `scripts/db_query_cr.sh` without `--commit` or through `read_bars`. Ask the owner once before Task 3 runs. No deploy, no schema apply, no committed run.
- The render step. A task that changes a file under `gcp/`, `lib/` or `scripts/` ends with it, because the generated inventory cites line numbers:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed), and stage whichever of the three docs changed with the code.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. The PR opens as a draft and stays one until every done_when line in its body is ticked with evidence. Every new test has a red then green record in the PR body: failing output before the code, passing output after.
- Choices this plan makes where the spec leaves one open (reported to the owner with the plan):
  - `flag_lock_key` and `flag_months_overlapping` live in `gcp/fetchers/intraday_bar_flags.py`; `replace_month` imports them inside the function. `gcp.database` imports nothing from the fetchers: it receives plain ints.
  - The coverage read of Design 3 step 4 runs in a dry run too, once per ticker, outside the month's transaction (Capacity counts 144 round trips for a 143-month dry run). "Only the read" in done_when[5] is read as: per ticker-month.
  - `session_sha256` holds, per Eastern date, the `sha256` value of `gcp.bar_recompute.bars_basis` over that date's rows.
  - `--flag-bars-from` and `--flag-bars-to` with a value that is not `YYYY-MM`, and the flag combined with `--replace-months`, `--verify-months`, `--verify-basis` or `--export-bars-from`, are usage errors (exit 2), as `--export-bars-from` treats its own; the spec's five refusals exit 1 before any query.
  - The race test's stand-in replaces `isolated_prints` by `monkeypatch` on the name `intraday_bar_flags` calls, so `flag_months` must call it through its module attribute (`bar_prints.isolated_prints`), not through a name bound at import.

## done_when map

| done_when | What | Spec body calls it | Task |
|---|---|---|---|
| [0] | the rule on hand-written bars, the version pinned to the parameters | item 1 | 2 |
| [1] | `print_geometry`, and its agreement with `wick_excesses` | item 2 | 1, 2 |
| [2] | the ten known sessions, 64 regular-hours flags | item 3 | 3 |
| [3] | the clean sample | | 3 |
| [4] | half days, session part | | 5 |
| [5] | the pass: transaction, four statements, proof, log lines, `BARS-CHANGED` | | 5, 6 |
| [6] | the write statement and the replace's span clear on Postgres | item 14 | 6, 9, 10 |
| [7] | the race test and its negative controls | new in r2 | 11 |
| [8] | when the pass runs: the nightly and `--flag-bars-from` | item 15 | 7, 8 |
| [9] | `DERIVED_SPAN_TABLES`, `clear_span_tables`, `advisory_locks`, `REBUILD` lines | item 16 | 9, 10 |
| [10] | the manifest's `flags` | item 17 | 12 |
| [11] | the schema | | 4 |
| [12] | `make test`, the files left alone | | 13 |
| [13] | the PR-body measurements | item 13 | 13 |
| [14] | product record, site note, snapshot, inventory, audit, gate | | 14 |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **The live edge, night over night.** The current month's read ends at the last stored bar, so its last two bars are not judged. The next night they are judged, `last_judged_ts` moves forward, a flag on one of them is inserted, and no `BARS-CHANGED` is logged for the appended session. Task 6.
- **One bar flagged on both sides, and the high side.** done_when[0] writes out low-side cases only, and the history holds 290 bars flagged on both sides. A bar whose high and low are both 60 bp out gives two rows, each with its own reference and bound (`reference + threshold` on the high side), and the write keeps both. Tasks 2 and 6.
- **The edges of a session and of a month.** A bar at 09:30:00 ET is `regular` and one at 16:00:00 ET is `extended` (`[market_open, market_close)`); a bar on a weekend or a holiday is `extended`; a flag on the first or last bar of a month window is written by exactly one of the two months that read it. Task 5.
- **What an operator types.** `--symbol spy` is taken as SPY; `--flag-bars-from 2026-13`, `2026-1` and `202601` are usage errors; `INTRADAY_BAR_FLAGS=OFF` and ` Off ` skip the pass; and a nightly that runs before `apply-schema` (the flag tables absent) logs `bar flags failed (defect)`, still attempts the export and exits 1, with the fetched bars left written. Tasks 7 and 8.
- **A month with no bar, and a read too short to judge.** No row in the month window gives a coverage row with `bars_in_month` 0, `bars_judged` 0 and both judged instants NULL (the table's CHECK), and no flag; a read of four bars or fewer judges none and raises nothing. Tasks 2 and 6.

## File map

| File | Change | Task |
|---|---|---|
| `lib/bar_prints.py` | new: `RULE_VERSION`, `PARAMS`, `print_geometry`, `isolated_prints` | 1, 2 |
| `gcp/schema.sql` | the two tables of Design 2, appended | 4 |
| `gcp/fetchers/intraday_bar_flags.py` | new: `FLAG_TICKERS`, `flag_lock_key`, `flag_months_overlapping`, `flag_months` | 5, 6, 10 |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `main()` (`:1685-1708`), `_run_bar_flags`, `run_flag_bars_from`, the two flags; `DERIVED_SPAN_TABLES` (beside `:484-491`); `replace_month` (`:898-905`, `:923-928`), the `REBUILD` lines (`:1064-1068`) | 7, 8, 9, 10 |
| `gcp/database.py` | `replace_rows_in_window` (`:536`): `clear_span_tables`, `advisory_locks` | 9, 10 |
| `gcp/fetchers/export_intraday_bars.py` | `export_window` (`:477-567`): the coverage read and the `flags` key | 12 |
| `tests/lib/test_bar_prints.py` | new | 1, 2, 3 |
| `tests/fixtures/bar_prints/` | new: 26 ticker-session files and `sources.json` | 3 |
| `tests/gcp/test_intraday_bar_flags_schema.py` | new | 4 |
| `tests/gcp/test_intraday_bar_flags.py` | new | 5, 6, 7, 8 |
| `tests/integration/test_intraday_bar_flags_writes.py` | new | 6, 9 |
| `tests/integration/test_intraday_bar_flags_race.py` | new | 11 |
| `tests/gcp/test_intraday_replace_months.py` | added assertions only | 9, 10 |
| `tests/gcp/test_export_intraday_bars.py` | the four named sites and the stand-in readers | 12 |
| `tests/gcp/measure_intraday_bar_flags.py` | new: the local measurement | 13 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 1 to 12 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 14 |

---

### Task 1: `print_geometry`, the one place a wick is measured

Spec: Design 1 (reference, excess, judged; "What it agrees with"). Advances done_when[1].

**Files:**
- Create: `lib/bar_prints.py`
- Test: `tests/lib/test_bar_prints.py`

**Interfaces:**
- Consumes: `lib.level_calibration.wick_excesses(bars) -> np.ndarray` (`:310-325`, unchanged; the high-side values, then the low-side ones, in bar order).
- Produces: `print_geometry(bars: pd.DataFrame) -> pd.DataFrame`, one row per input bar in input order, columns `ts, reference_high, excess_high, reference_low, excess_low, judged`; price units, no threshold; NaN references and excesses where `judged` is False. Pure: pandas and numpy only.

- [ ] **Step 1: Write the failing tests**
  - `test_geometry_low_wick`: 9 bars, every open and close 100.00, high 100.05, low 100.00, bar 4's low 99.40. Assert row 4: `reference_low == 100.0`, `excess_low == pytest.approx(0.60)`, `reference_high == 100.0`, `excess_high == pytest.approx(0.05)`, `judged` True; `list(judged) == [False, False, True, True, True, True, True, False, False]`; rows 0, 1, 7, 8 hold NaN in the four value columns; `list(out.ts) == list(bars.ts)`.
  - `test_geometry_own_open_or_close_is_left_out_only_when_it_is_the_extreme`: bar 4 opens at 99.40 (its low) and closes at 100.00: `reference_low == 100.0`. Bar 4 opens and closes at 99.40, low 99.40: `reference_low == 100.0` (the neighbours' bodies alone).
  - `test_geometry_agrees_with_wick_excesses`: 300 bars written by a seeded formula in the test, each open and close strictly inside its own high and low. With `g = print_geometry(bars)`, `w = wick_excesses(bars)`, `j = g.judged.to_numpy()`: `np.array_equal(g.excess_high[j].to_numpy(), w[:300][j])` and the same for `excess_low` against `w[300:]`. Exact equality, no tolerance.
  - `test_geometry_bad_input`: an empty frame returns an empty frame with the six columns; a NaN in each of `open`, `high`, `low`, `close` raises `ValueError` whose message holds that bar's `ts`; `ts` equal or decreasing raises `ValueError`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_bar_prints.py -q` (expect FAIL: no module `lib.bar_prints`).
- [ ] **Step 3: Implement `print_geometry`** in `lib/bar_prints.py`. Low reference: the lowest open or close of bars `i-2`, `i-1`, `i+1`, `i+2`, together with whichever of the bar's own open and close is above its low; high side mirrored. `excess_low = reference_low - low`, `excess_high = high - reference_high`. Vectorised; no loop over bars. To meet the exact-equality test, form the high-side excess with the same operations `wick_excesses` uses where both apply.
- [ ] **Step 4: Run** the same command (expect 4 passed), then the render step.
- [ ] **Step 5: Commit:** `feat(data): measure a 1-minute bar's wick against its neighbourhood`

### Task 2: `isolated_prints`, the scale, the threshold and the version

Spec: Design 1 (scale, threshold, bound, flagged, print_kind, excess_bp, columns); decisions 1 to 3. Advances done_when[0] and closes done_when[1].

**Files:**
- Modify: `lib/bar_prints.py`
- Test: `tests/lib/test_bar_prints.py`

**Interfaces:**
- Consumes: `print_geometry` (Task 1).
- Produces: `RULE_VERSION = "isolated-print-v1"`; `PARAMS = {"neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0, "floor_bp": 50.0}`; `isolated_prints(bars: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]` returning `(flags, judged)`, `flags` with columns `ts, side, print_kind, observed, reference, bound, scale, excess_bp`, one row per flagged (bar, side), `side` in `("high", "low")`, `print_kind` in `("wick", "open", "close", "open_and_close")`; `judged` a boolean array, one value per input bar.

- [ ] **Step 1: Write the failing tests.** A helper `flat(n)` builds `n` bars with open and close 100.00, high 100.05, low 100.00 (range 0.05). Each case writes its expected rows as literals:
  - `test_low_wick_60bp`: bar 30 of `flat(61)` has low 99.40. One flag: `side "low"`, `print_kind "wick"`, `observed 99.40`, `reference 100.0`, `scale 0.05`, `bound 99.50` (100 minus `max(6 x 0.05, 0.0050 x 100)`), `excess_bp == pytest.approx(60.0)`.
  - `test_open_close_and_one_price`: open 99.40 with close 100 is `"open"`; close 99.40 with open 100 is `"close"`; open, high, low and close all 99.40 is `"open_and_close"`.
  - `test_five_consecutive_wicks`: bars 28 to 32 have low 99.40, opens and closes at 100: five flags.
  - `test_level_shift_is_not_flagged`: bar 30 and every bar after it open and close at 99.40: `len(flags) == 0`.
  - `test_under_the_floor_and_at_the_bound`: low 99.51 (49 bp) gives no flag; low 99.50, exactly the bound, gives no flag.
  - `test_wide_scale`: the same 60 bp wick where every bar's range is 0.15 (6 x 0.15 = 0.90 above 0.60): no flag.
  - `test_ends_are_not_judged`: `judged[:2]` and `judged[-2:]` are False, the rest True, and `np.array_equal(judged, print_geometry(bars).judged)`.
  - `test_flags_rest_on_print_geometry`: over the bars of the cases above, each flag's `reference` equals `print_geometry`'s for its `ts` and side, and its `excess_bp` equals that side's excess divided by the reference times 10,000.
  - `test_bad_input`: NaN in each price column raises `ValueError` naming the `ts`; `ts` not strictly increasing raises `ValueError`; an empty input returns an empty frame with the eight columns and an empty array.
  - `test_version_pins_the_parameters`: `RULE_VERSION == "isolated-print-v1"` and `PARAMS == {"neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0, "floor_bp": 50.0}`.
  - Review Focus: `test_high_side_and_both_sides`: bar 30 has high 100.60 and low 99.40: two rows, the high one with `bound 100.50` and `observed 100.60`. `test_short_input`: four bars return no flag and `judged` all False, with no exception.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_bar_prints.py -q` (expect FAIL: `isolated_prints` not defined).
- [ ] **Step 3: Implement** the constants and `isolated_prints`. Scale: the median of `high - low` over the 61 stored bars centred on the bar, fewer at the two ends of the input (a centred rolling median with `min_periods=1`). Every constant is read from `PARAMS`; no literal 6, 50, 61 or 2 elsewhere in the module.
- [ ] **Step 4: Run** the same command (expect all passed), then the render step.
- [ ] **Step 5: Commit:** `feat(data): flag a print isolated from its minute (isolated-print-v1)`

### Task 3: The labelled sessions

Spec: Design 1; Problem 4; Implementation plan items 3 and 4. Closes done_when[2] and done_when[3], and supplies the half-day files Task 5 reads. Read-only production access: ask the owner once before the exports.

**Files:**
- Create: `tests/fixtures/bar_prints/<TICKER>_<YYYY-MM-DD>.csv` (26 files), `tests/fixtures/bar_prints/sources.json`
- Test: `tests/lib/test_bar_prints.py`

**Interfaces:**
- Consumes: `isolated_prints` (Task 2); `lib.eastern_time.session_schedule` for the regular-hours cut in the test.
- Produces: `load_session(ticker: str, day: str) -> pd.DataFrame` in the test module (columns `ts, open, high, low, close, volume, inserted_at`, `ts` tz-aware UTC), which Task 5 imports.

- [ ] **Step 1: Export** each file with `./scripts/db_query_cr.sh -q "<SQL>"`, no `--commit`: one Eastern day of one ticker plus the 40 stored bars before and the 40 after it, the columns of the pass's read, `ORDER BY ts`. The 26: the ten known sessions (SPY 2017-11-28, 2018-02-06, 2018-02-20, 2018-04-05, 2023-05-25; QQQ 2018-02-06, 2021-12-14, 2023-05-25; IWM 2018-02-06, 2023-05-25), the twelve clean ones (SPY, QQQ, IWM on 2019-06-17, 2020-03-12, 2022-09-13, 2024-08-05) and the four half days (SPY 2025-07-03, SPY 2025-12-24, IWM 2018-12-24, IWM 2025-11-28). `sources.json` names, per file, the db-query execution id, the SQL, the row count and the file's sha256.
- [ ] **Step 2: Write the tests** (they pass at once if Task 2 is right; a failure here is a finding about the rule, reported to the owner, never a changed expectation):
  - `test_sources_json_matches_the_files`: every file's sha256 and row count equal its `sources.json` entry, and the directory holds exactly the 26 files.
  - `test_known_sessions`: parametrised over the ten; the regular-hours flags, as `(HH:MM ET, side)`, equal the literal list in the test: SPY 2017-11-28 `[("15:16", "low")]`; SPY 2018-02-06 22 rows, all low, first 15:13 and last 15:42, every time written out; SPY 2018-02-20 `[("09:31", "low")]`; SPY 2018-04-05 `[("11:37", "low")]`; SPY 2023-05-25 16, all low, 15:29 among them, every time written out; QQQ 2018-02-06 15:30, 15:32, 15:39, 15:40, 15:41 low; QQQ 2021-12-14 `[("11:16", "low")]`; QQQ 2023-05-25 14:15, 14:16, 14:49, 15:53 low; IWM 2018-02-06 15:22, 15:35, 15:37 low; IWM 2023-05-25 ten, all high, 13:22 among them, every time written out. A last assertion: the ten lists hold 64 rows. The times the spec does not list (SPY 2018-02-06, SPY 2023-05-25, IWM 2023-05-25) are copied once from the first run's output into the test and checked against the spec's count, first, last and named members.
  - `test_clean_sample`: no regular-hours flag in any of the twelve files; no flag at any hour in the three 2019-06-17 files.
- [ ] **Step 3: Run:** `python3 -m pytest tests/lib/test_bar_prints.py -q` (expect all passed). Record the red: with `PARAMS["scale_multiple"]` set to 8.0, `test_known_sessions[QQQ-2021-12-14]` fails (the spec's decision 2); revert.
- [ ] **Step 4: Commit:** `test(data): pin the rule on ten known sessions and a clean sample`

### Task 4: The two tables

Spec: Design 2. Closes done_when[11].

**Files:**
- Modify: `gcp/schema.sql` (append; `:140-168`, the `market_data_intraday` DDL, untouched)
- Test: `tests/gcp/test_intraday_bar_flags_schema.py`

**Interfaces:**
- Produces: tables `intraday_bar_flags` (primary key `ticker, interval, ts, side, rule_version`) and `intraday_bar_flag_coverage` (primary key `ticker, interval, ts, rule_version`), with the columns, defaults and CHECK constraints of Design 2's DDL, copied verbatim.

- [ ] **Step 1: Write the failing test** (text-level, in the style of `tests/gcp/test_bar_recompute_schema.py`): both `CREATE TABLE IF NOT EXISTS` statements exist; each column of Design 2 appears with its type and `NOT NULL` where the spec has it; the CHECKs on `side`, `print_kind`, `session_part`, `read_start < read_end` and `(bars_judged = 0) = (first_judged_ts IS NULL)` are present; both primary keys match; and the text of `gcp/schema.sql` from `CREATE TABLE` of `market_data_intraday` through its partitions and index equals, byte for byte, the same span of `git show origin/main:gcp/schema.sql`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_intraday_bar_flags_schema.py -q` (expect FAIL: table not found).
- [ ] **Step 3: Add** the DDL of Design 2 to `gcp/schema.sql`, comments included.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/gcp/test_apply_schema.py -q` (expect passed).
- [ ] **Step 5: Commit:** `feat(data): add the bar flag and flag coverage tables`

### Task 5: The pass reads, proves, judges and labels (dry run)

Spec: Design 3 steps 1 to 3 and 6; Design 9. Advances done_when[5]; closes done_when[4].

**Files:**
- Create: `gcp/fetchers/intraday_bar_flags.py`
- Test: `tests/gcp/test_intraday_bar_flags.py`

**Interfaces:**
- Consumes: `lib.bar_prints` (as the module, so a test can replace `isolated_prints`); `gcp.database.get_engine`; `lib.eastern_time.intraday_month_window`, `session_schedule`, `market_date`; `gcp.bar_recompute.require_proven`, `UnprovenRows`; `load_session` (Task 3).
- Produces:
  - `FLAG_TICKERS = ("SPY", "QQQ", "IWM")`
  - `flag_months(tickers: Sequence[str], months: Sequence[tuple[int, int]], *, commit: bool, now_utc: datetime | None = None) -> dict` returning `{"months": int, "flags": int, "changed": int, "seconds": float}`
  - `judge_month(bars: pd.DataFrame, month: tuple[int, int]) -> tuple[pd.DataFrame, dict]`: the flags inside the month window, with `session_part` added, and the month's counts (`bars_in_month`, `bars_judged`, `first_judged_ts`, `last_judged_ts`, and the four `flags_<part>_<side>`). Pure but for the calendar.

- [ ] **Step 1: Write the failing tests.** A recording stand-in for the engine's connection answers the read from a frame the test gives and records every statement's text and parameters.
  - `test_half_days`: over the four half-day files, every bar from 13:00 to 20:00 ET is labelled `extended`; none has a regular-hours flag; the flags from 13:00 to 16:00 ET are exactly SPY 2025-07-03 13:01, 13:06, 13:58, 13:59 (`low`, `wick`); SPY 2025-12-24 14:21 (`low`, `close`, `observed == 670.292`); IWM 2018-12-24 none; IWM 2025-11-28 13:17 (`low`, `close`) and 14:50 (`low`, `open`, `observed == 233.4998`).
  - `test_dry_run_issues_only_the_read`: `flag_months(("SPY",), [(2023, 5)], commit=False)` records, for the month, exactly one statement; it holds `interval = '1min'`, selects `ts, open, high, low, close, volume, inserted_at`, and its `start` and `end` are `intraday_month_window(2023, 5)` widened by 7 days on each side; no text holds `set_config`, `pg_advisory`, `INSERT` or `DELETE`; the transaction is rolled back.
  - `test_flags_outside_the_month_window_are_not_kept` and `test_two_months_equal_one_read`: over a two-month fixture written in the test, the union of the two months' flags equals `isolated_prints` over the two months read whole.
  - `test_unproven_rows`: a month holding one row for which `lib.eastern_time.proven_true_utc` is False raises `UnprovenRows`.
  - `test_read_failures_propagate`: a read raising `ConnectionError("connection refused")` and one raising `KeyError("high")` each propagate unchanged out of `flag_months`.
  - `test_refuses_other_tickers`: `flag_months(("AAPL",), ...)` raises `ValueError` and the stand-in recorded no statement.
  - `test_month_log_line`: one `caplog` line per month starting `bar flags month:`, with the ticker, `YYYY-MM`, `judged=` and the four counts, in the spec's form `bar flags month: SPY 2026-10 judged=20412 regular_high=0 regular_low=1 extended_high=7 extended_low=12 (3/6)`.
  - Review Focus: `test_session_edges`: a flagged bar at 09:30:00 ET is `regular`, at 16:00:00 ET `extended`, on a Saturday `extended`, on 2025-12-25 `extended`. `test_month_edge_bar_belongs_to_one_month`: a flag on the first bar of June's window is in June's result and not in May's.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_intraday_bar_flags.py -q` (expect FAIL: no module).
- [ ] **Step 3: Implement** the module: one transaction on one connection per ticker-month, in month order; the read on that connection; `require_proven`; `judge_month`; the log line. `session_schedule` is called once per month read, not once per bar.
- [ ] **Step 4: Run** the same command (expect all passed), then the render step.
- [ ] **Step 5: Commit:** `feat(data): judge a ticker-month of bars for isolated prints`

### Task 6: The pass locks, writes and compares (committed run)

Spec: Design 3 steps 1, 4 and 5; Design 2 (`bars_basis`, `session_sha256`, `run_id`, `code_version`); decision 12 on the pass's side. Closes done_when[5]; advances done_when[6] (every clause but the replace's).

**Files:**
- Modify: `gcp/fetchers/intraday_bar_flags.py`
- Test: `tests/gcp/test_intraday_bar_flags.py`, `tests/integration/test_intraday_bar_flags_writes.py` (new)

**Interfaces:**
- Consumes: Task 5; `gcp.bar_recompute.bars_basis`, `run_id`, `code_version`; `lib.bar_prints.RULE_VERSION`, `PARAMS`.
- Produces:
  - `flag_lock_key(ticker: str, month: tuple[int, int]) -> int`
  - `LOCK_TIMEOUT = "120s"`
  - `write_month_sql() -> str`: the one write statement (a data-modifying CTE that deletes the stale flags, upserts the new set keeping `detected_at`, upserts the coverage row, and returns the counts deleted, inserted and updated)
  - `flag_months(..., commit=True)` issuing per ticker-month, in order: `SELECT set_config('lock_timeout', '120s', true), current_setting('transaction_isolation')`; `SELECT pg_advisory_xact_lock(:k)`; the read; the write. And once per ticker, before its first month, one strict coverage read over the run's months for `RULE_VERSION`.

- [ ] **Step 1: Write the failing unit tests** (recording stand-in):
  - `test_lock_key`: `flag_lock_key("SPY", (2023, 5)) == 2323874143540971683`; the keys of the three tickers over 2015-01 to 2026-11 are 429 distinct ints, each within the signed 64-bit range.
  - `test_commit_issues_four_statements_in_order`: for one ticker-month the recorded texts are, in order, the configuration select, the lock select with `k == flag_lock_key(...)`, the read, one write; the lock is its own statement and the read's text holds no `pg_advisory`.
  - `test_other_isolation_raises_before_the_lock`: the configuration statement answering `repeatable read` raises; no lock, read or write was recorded.
  - `test_a_failing_month_leaves_earlier_months_written`: three months, the second read raising `ConnectionError`: the first month's write was committed, nothing was written for the second, the third was not started.
  - `test_coverage_row_holds_the_read_window_and_the_session_digests`: the write's parameters hold `read_start` and `read_end` (the widened window), `params == PARAMS`, `bars_basis`, and `session_sha256` with one key per Eastern date of the rows read.
  - `test_bars_changed`: an earlier coverage row whose `session_sha256` differs on one date both hold logs one line `BARS-CHANGED SPY 2026-10 sessions=2026-10-14 since=<checked_at>`, and with `commit=True` the line also gives the inserted and deleted counts from the write's own result; a date the earlier row holds and the read does not is named too; a date only the read holds logs nothing.
  - Review Focus: `test_live_edge_night_over_night`: night one reads a month ending at bar N; night two reads the same bars plus one more session whose bar N-1 is a 60 bp wick. Night two logs no `BARS-CHANGED`, its `last_judged_ts` is later, and its write's set holds the new flag.
- [ ] **Step 2: Write the failing integration test** `tests/integration/test_intraday_bar_flags_writes.py` (real Postgres, own rows wiped as `test_intraday_replace_spare.py` does):
  - a first pass inserts the flags with `detected_at == checked_at ==` the pass's `now_utc`;
  - a second pass with a later `now_utc` over unchanged bars leaves every column as it was except `checked_at` and `run_id`; `detected_at` is the first pass's;
  - after a bar is changed so one flag no longer holds and another's `observed` moved: the first is deleted, the second holds its new `observed, reference, bound, scale, excess_bp, checked_at, run_id` and its old `detected_at`;
  - flags of another `rule_version`, of another ticker and of the neighbouring months are byte for byte as seeded;
  - a month with no flag writes its coverage row with the four counts 0 and `bars_judged > 0`;
  - Review Focus: a month with no bar writes a coverage row with `bars_in_month == 0`, `bars_judged == 0` and both judged instants NULL; a bar flagged on both sides is stored as two rows.
- [ ] **Step 3: Run:** `python3 -m pytest tests/gcp/test_intraday_bar_flags.py -q` (expect FAIL), and with a local Postgres loaded with `gcp/schema.sql`, `python3 -m pytest tests/integration/test_intraday_bar_flags_writes.py -q` (expect FAIL). Without a local Postgres the integration red and green are CI's `integration-tests` job; say so in the PR body.
- [ ] **Step 4: Implement.** The new set is passed to the one statement as arrays (or one JSONB parameter) and unnested, so the statement count does not grow with the flags. An empty set runs the same statement.
- [ ] **Step 5: Run** both commands (expect passed), then the render step.
- [ ] **Step 6: Commit:** `feat(data): write a month's flags and coverage in one locked statement`

### Task 7: The nightly pass

Spec: Design 4; Design 5; decisions 5 and 6. Advances done_when[8] (the nightly half). With this task the owner's first priority is on the branch.

**Files:**
- Modify: `gcp/fetchers/fetch_alphavantage_intraday.py` (`main()`, the block at `:1685-1708`; a helper beside `_run_bars_export`, `:1443`)
- Test: `tests/gcp/test_intraday_bar_flags.py`

**Interfaces:**
- Consumes: `flag_months`, `FLAG_TICKERS` (Tasks 5 and 6); `export_intraday_bars.nightly_months`; `lib.eastern_time.market_today`; `lib.infra_errors.is_infrastructure_error`.
- Produces: `_run_bar_flags(tickers: Sequence[str], months: Sequence[tuple[int, int]]) -> bool`, True only when the pass returned; `main()` calls it inside the nightly block, after the fetch loop and before `_run_bars_export`, and exits 1 when it returned False.

- [ ] **Step 1: Write the failing tests** (`main()` run with `monkeypatch`ed `sys.argv`, a stubbed fetch, and recorders for `flag_months` and `_run_bars_export`):
  - `test_nightly_runs_the_pass_after_the_fetch_and_before_the_export`: with `--symbol=ALL --force`, one task and the database configured, the recorded order is every `process_symbol` call, then `flag_months(("SPY", "QQQ", "IWM"), nightly_months(market_today()), commit=True)`, then the export.
  - `test_switch_off`: `INTRADAY_BAR_FLAGS=off` logs one line naming the variable, calls no `flag_months`, and the export still runs.
  - `test_other_shapes_flag_nothing`: no `--force`; `--start-date`; `--symbols-file`; two tasks: `flag_months` is never called.
  - `test_outage_and_defect`: a pass raising `ConnectionError` logs a line starting `bar flags failed (outage)`, one raising `KeyError` a line starting `bar flags failed (defect)`; in both the export still runs and `main()` exits 1.
  - `test_summary_line`: after a pass that returns, one line starting `bar flags:` with the months, the flags and the seconds, in the form `bar flags: 6 months, 41 flags, 2 changed, 9.8 s`.
  - `test_the_pass_reads_what_the_refetch_left`: a stored session holding values B, a coverage row whose `session_sha256` is that of values A, and a stubbed fetch that upserts A: the pass reads A and logs no `BARS-CHANGED`; a stubbed fetch that upserts A' logs `BARS-CHANGED` naming that session.
  - Review Focus: `test_switch_letter_case`: `OFF` and ` Off ` skip the pass. `test_flag_tables_absent`: a pass raising the error a missing relation gives logs `bar flags failed (defect)`, the export is still attempted, and the exit is 1.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_intraday_bar_flags.py -q` (expect FAIL: `flag_months` never called).
- [ ] **Step 3: Implement** `_run_bar_flags` on the pattern of `_run_bars_export` (`:1443-1464`) and the call in `main()`. The database-not-configured branch skips the pass with one log line, as it skips the export.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/gcp/test_export_intraday_bars.py tests/gcp/test_av_intraday_universe.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(data): judge the two months the nightly fetch rewrote`

### Task 8: `--flag-bars-from` and `--flag-bars-to`

Spec: Design 6; decision 7; Capacity (two committed executions a ticker). Closes done_when[8].

**Files:**
- Modify: `gcp/fetchers/fetch_alphavantage_intraday.py` (argparse at `:1553-1580`; a runner beside `run_export_bars_from`, `:1467`)
- Test: `tests/gcp/test_intraday_bar_flags.py`

**Interfaces:**
- Consumes: `flag_months`, `FLAG_TICKERS`.
- Produces: `run_flag_bars_from(first: tuple[int, int], last: tuple[int, int] | None, symbol: str, commit: bool) -> int` (the process exit code); arguments `--flag-bars-from YYYY-MM`, `--flag-bars-to YYYY-MM`, and the module's existing `--commit`.

- [ ] **Step 1: Write the failing tests:**
  - `test_history_months`: `--flag-bars-from 2015-01 --symbol SPY` with the Eastern month stubbed to 2026-11 calls `flag_months(("SPY",), <143 months, 2015-01 to 2026-11>, commit=False)`; with `--flag-bars-to 2020-12`, 72 months; with `--symbol ALL`, the three tickers; with `--commit`, `commit=True`. No fetch function is called and no API key is read.
  - `test_refusals_exit_1_before_any_query`: `--symbol AAPL`; `CLOUD_RUN_TASK_COUNT=2`; the database not configured; `--flag-bars-from` a month after the current one; `--flag-bars-to` before `--flag-bars-from`; `--flag-bars-to` without `--flag-bars-from`: each exits 1 and `flag_months` was not called.
  - `test_usage_errors`: together with `--replace-months`, `--verify-months`, `--verify-basis` or `--export-bars-from`: `SystemExit(2)`.
  - Review Focus: `--symbol spy` runs SPY; `--symbol SPY,QQQ` is refused; `--flag-bars-from` given `2026-13`, `2026-1` or `202601` is a usage error.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_intraday_bar_flags.py -q` (expect FAIL: unrecognised argument).
- [ ] **Step 3: Implement,** mirroring `run_export_bars_from` (`:1467-1511`) and its argument checks.
- [ ] **Step 4: Run** the same command (expect passed), then the render step.
- [ ] **Step 5: Commit:** `feat(data): add the history run of the bar flag pass`

### Task 9: A replace clears the flags by read span

Spec: Design 7 (first five bullets); decision 8. Advances done_when[9] and done_when[6] (the replace's clauses).

**Files:**
- Modify: `gcp/database.py` (`replace_rows_in_window`, `:536`; the clears at `:695-705`), `gcp/fetchers/fetch_alphavantage_intraday.py` (`DERIVED_SPAN_TABLES` after `:491`; both swaps of `replace_month`, `:898-905` and `:923-928`; the `REBUILD` lines, `:1064-1068`)
- Test: `tests/gcp/test_intraday_replace_months.py` (added assertions; `:875` and `:1634` unchanged), `tests/integration/test_intraday_bar_flags_writes.py`

**Interfaces:**
- Consumes: Task 4's tables; Task 6's `flag_months` (the integration test seeds through it).
- Produces: `replace_rows_in_window(..., clear_span_tables: Sequence[str] = ())`: in the swap's transaction, after the `clear_tables` deletes, `DELETE FROM <t> WHERE <clear_key columns match> AND read_start < :w_end AND read_end > :w_start`, counted in `cleared`; a name that fails the identifier check is refused before the transaction opens; a table that does not exist is skipped. `DERIVED_SPAN_TABLES = ("intraday_bar_flags", "intraday_bar_flag_coverage")`.

- [ ] **Step 1: Write the failing tests:**
  - in `test_intraday_replace_months.py`: `DERIVED_TS_TABLES` still holds its fifteen names; both swaps of `replace_month`, the window's and the tail's, receive `clear_span_tables == DERIVED_SPAN_TABLES`; `clear_span_tables=("bad name;",)` raises before the transaction opens (as `:881-891` does for `clear_tables`); a committed replace of one month prints `REBUILD intraday_bar_flags rows_cleared=N` and `REBUILD intraday_bar_flag_coverage rows_cleared=N` where it cleared rows.
  - in the integration file: four consecutive months of one ticker written by `flag_months`, beside a second ticker's; `replace_rows_in_window` over `market_data_intraday` with the third month's window and `clear_span_tables=DERIVED_SPAN_TABLES` leaves, before any rebuild, the first month's coverage row only for that ticker, the first month's flags, and every row of the second ticker; a swap whose `verify` raises leaves all four months' flags and coverage as they were; `flag_months` over the second to fourth months afterwards writes their coverage rows again.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_intraday_replace_months.py -q` (expect FAIL: unexpected keyword `clear_span_tables`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/gcp/test_intraday_replace_levels_tables.py -q` (expect passed, the file unmodified), then the render step.
- [ ] **Step 5: Commit:** `feat(data): clear a month's flags when a replace rewrites bars they rest on`

### Task 10: The replace takes the pass's locks

Spec: Design 7, "Coordination with the pass"; decision 12; issue #1982. Closes done_when[9]; advances done_when[6] (its last clause) and done_when[7].

**Files:**
- Modify: `gcp/fetchers/intraday_bar_flags.py`, `gcp/database.py` (`replace_rows_in_window`; `SET LOCAL lock_timeout` at `:681-683`), `gcp/fetchers/fetch_alphavantage_intraday.py` (`replace_month`)
- Test: `tests/gcp/test_intraday_replace_months.py`, `tests/gcp/test_intraday_bar_flags.py`

**Interfaces:**
- Consumes: `flag_lock_key` (Task 6).
- Produces:
  - `flag_months_overlapping(start: datetime, end: datetime) -> list[tuple[int, int]]`: the months whose read window `[month start - 7 days, month end + 7 days)` overlaps `[start, end)`, ascending, by the span clear's own predicate.
  - `replace_rows_in_window(..., advisory_locks: Sequence[int] = ())`: given any, the transaction first runs `SET LOCAL lock_timeout = '30s'`, then one `SELECT current_setting('transaction_isolation'), pg_advisory_xact_lock(:k0), pg_advisory_xact_lock(:k1), ...` with the keys ascending, and raises before any row lock when the isolation is not `read committed`; a key that is not an `int` in the signed 64-bit range raises `ValueError` before the transaction opens.
  - `replace_month` passes `advisory_locks=[flag_lock_key(symbol, m) for m in flag_months_overlapping(start, end)]` to the window's swap, and the same over `[end, tail_end)` to the tail's, for every ticker.

- [ ] **Step 1: Write the failing tests:**
  - `test_months_overlapping`: for the window of 2023-05, `[(2023, 4), (2023, 5), (2023, 6)]`; for a tail `[end of May's window, + 1 day)`, `[(2023, 5), (2023, 6)]`; an empty span returns `[]`.
  - `test_the_swaps_receive_their_locks`: the window's swap of month M receives the keys of M-1, M and M+1 and the tail's those of M and M+1.
  - `test_lock_statement_precedes_the_row_lock`: given `advisory_locks`, the recorded statements are `SET LOCAL lock_timeout = '30s'`, then one select naming `pg_advisory_xact_lock` once per key with the keys ascending, then the row-lock statement, then any `DELETE`; the same with and without `verify`; with no `advisory_locks` no such select is issued.
  - `test_other_isolation_raises_before_any_row_lock`, and `test_bad_keys_are_refused`: `"1"`, `1.0`, `True`, `2**63` and `-2**63 - 1` each raise `ValueError` before the transaction opens.
  - in the integration file (done_when[6], last clause): every flag and coverage row the span clear deleted belongs to a month in `flag_months_overlapping` of the swapped window.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_intraday_replace_months.py tests/gcp/test_intraday_bar_flags.py -q` (expect FAIL: unexpected keyword `advisory_locks`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/gcp/test_intraday_replace_levels_tables.py tests/gcp/test_intraday_writers_utc.py -q` (expect passed), then the render step.
- [ ] **Step 5: Commit:** `fix(data): hold a month's flag lock across a replace of its bars`

### Task 11: The race test and its negative controls

Spec: decision 12; Approaches considered; Design 3 step 1; Design 7. Closes done_when[7] and done_when[6].

**Files:**
- Create: `tests/integration/test_intraday_bar_flags_race.py`

**Interfaces:**
- Consumes: `flag_months`, `flag_lock_key`, `flag_months_overlapping`, `replace_rows_in_window(..., clear_span_tables=, advisory_locks=, verify=)`, `DERIVED_SPAN_TABLES`.
- Produces: nothing a later task uses.

- [ ] **Step 1: Write the test.** Two connections in two threads; a third polls `pg_locks`. The pass is held between its read and its write by a `monkeypatch`ed `bar_prints.isolated_prints` that waits on a `threading.Event`; the replace is held by a `verify` that waits on another. Every wait has a timeout that fails the test, never a bare `sleep`. Four months of one ticker seeded and judged first.
  - `test_read_first` (a): the pass holds the third month's lock and has read; the replace of that month is started; within 10 s `pg_locks` shows an ungranted advisory lock and the bars are unchanged; the pass is released and commits; the replace commits; coverage and flags of the second to fourth months are absent.
  - `test_replace_first` (b): the replace holds its locks before it swaps; the pass of the third month is started and seen waiting on an ungranted advisory lock; the replace is released, swaps and commits; the pass's coverage row holds the `bars_basis` and `session_sha256` of the new bars.
  - `test_negative_control_no_lock` (c): case (a) with the pass's lock statement replaced by `SELECT 1` ends with the third month's coverage row, computed from the old bars, present after the replace committed. The assertion is that the stale row exists.
  - `test_negative_control_lock_inside_the_read` (d): case (b) with the lock moved into the read as a CTE ends with the old bars' `bars_basis`.
  - `test_replace_lock_timeout`: a replace that waits past its 30 s `lock_timeout` raises and commits nothing: the bars, flags and coverage are as before.
- [ ] **Step 2: Run:** `python3 -m pytest tests/integration/test_intraday_bar_flags_race.py -q` against a local Postgres loaded with `gcp/schema.sql` (expect 5 passed; (c) and (d) pass by showing the race). Record the red: with `advisory_locks` dropped from the replace in the test's call, (a) fails.
- [ ] **Step 3: Commit:** `test(data): interleave the flag pass and a replace on real Postgres`

### Task 12: The counts in the bucket manifest

Spec: Design 8; decision 9. Closes done_when[10].

**Files:**
- Modify: `gcp/fetchers/export_intraday_bars.py` (`export_window`, `:477-567`)
- Test: `tests/gcp/test_export_intraday_bars.py` (`fake_query` at `:112`; assertions at `:648`, `:821`, `:838-839`, `:1617-1618`; stand-in readers at `:874-881`, `:1583-1585`, `:1782-1787`)

**Interfaces:**
- Consumes: `lib.bar_prints.RULE_VERSION`, imported inside `export_window`; table `intraday_bar_flag_coverage`.
- Produces: each month entry gains `"flags"`: `{"rule_version", "checked_at", "bars_judged", "regular_high", "regular_low", "extended_high", "extended_low"}`, or `{"state": "not_judged"}`. Manifest version stays 1.

- [ ] **Step 1: Change and add the tests:**
  - `fake_query` answers SQL naming `intraday_bar_flag_coverage` from a frame the test gives, empty by default; the three stand-in readers answer it with an empty frame, the second recording it as `"coverage"`.
  - `:648`: the expected entry gains `"flags": {"state": "not_judged"}`.
  - `test_io_shape`: the nightly's tuple at `:821` becomes `(6, 3, 12)`; the calls at `:838-839` and `:1617-1618` gain one coverage read per ticker, right after that ticker's daily read; added assertions: three coverage reads in the order SPY, QQQ, IWM, each with the ticker, `RULE_VERSION` and the run's first and last month as parameters and `timeout_s=120`; the history's one.
  - `test_flags_from_a_coverage_row`: a coverage row for one month gives that entry the seven keys with the row's values; the other month of the run reads `{"state": "not_judged"}` and never a 0.
  - `test_coverage_read_failure_leaves_the_manifest`: the coverage query raising `ConnectionError` makes `export_window` raise and the manifest object is unchanged.
  - `test_read_bars_returns_the_key_as_stored`, and the module's top-level imports are still the standard library and pandas.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect FAIL on the changed and added tests only).
- [ ] **Step 3: Implement:** one `query_to_dataframe_strict(sql, params, timeout_s=120)` per ticker over the run's months, after that ticker's daily read.
- [ ] **Step 4: Run** the same command (expect all passed), then `git diff origin/main -- tests/gcp/test_export_intraday_bars.py | grep '^-.*assert'` shows removed assertions only at the four named sites; then the render step.
- [ ] **Step 5: Commit:** `feat(data): record each month's flag counts in the bars manifest`

### Task 13: Measurements, the whole suite, the files left alone

Spec: Done when (the PR-body measurements; `make test`); Capacity. Closes done_when[12]; produces done_when[13], posted in Task 14.

**Files:**
- Create: `tests/gcp/measure_intraday_bar_flags.py`

- [ ] **Step 1: Local measurement.** `python3 tests/gcp/measure_intraday_bar_flags.py`: `flag_months` with `commit=True` over one ticker's 72 synthetic months of 31,711 rows each, the database stubbed. It prints the seconds, the statement count and the peak resident memory, and exits non-zero unless the count is 289 and the memory is under 512 MB.
- [ ] **Step 2: Production, read-only** (`scripts/db_query_cr.sh`, no `--commit`): `EXPLAIN (ANALYZE, BUFFERS)` of the pass's read for SPY 2023-05 with its margins, written with literals. Expect an index scan whose `rows=` equals the rows returned (the spec measured 27,717 rows, 671 buffers, 242 ms, db-query-nbpxc). Keep the execution id.
- [ ] **Step 3: The shipped rule over the bucket copy.** Through `read_bars` over `gs://<GCS_BUCKET>/intraday-bars/v1/1min/`, run `isolated_prints` per ticker and tabulate the flag rows by session part and side beside the spec's prototype figures (16,441 rows in all, 445 in regular hours, 15,996 in extended). Every difference is named bar by bar; a difference is reported to the owner, not explained away.
- [ ] **Step 4: Run:** `make test` in its normal order (expect no failure `origin/main` does not have).
- [ ] **Step 5: Run:** `git diff --stat origin/main -- lib/eastern_time.py lib/indicators.py lib/level_calibration.py gcp/bar_recompute.py gcp/fetchers/fetch_market_data.py gcp/deploy.sh platform/api CLAUDE.md tests/meta/test_production_writers.py tests/meta/test_timezone_boundaries.py tests/fixtures/timezone_boundary_baseline.json tests/gcp/test_av_intraday_universe.py tests/gcp/test_intraday_writers_utc.py tests/gcp/test_intraday_replace_levels_tables.py` (expect empty).
- [ ] **Step 6: Commit:** `test(data): measure the flag pass over a synthetic history`

### Task 14: Close: product record, site note and the gate

Spec: Site traceability (Design 12); Done when (the last item); product-delivery Phase 4 and Phase 5. Closes done_when[13] (posted) and done_when[14]. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them: the source hash covers those paths.

- [ ] Push with `git push -u origin feature/feat-data-001-bar-misprint-flags` and open a **draft** PR. Body: the spec's and this plan's paths; the 15 done_when items as `- [ ]` lines; `Red then green`; a Capacity section (Volume, Velocity, Wall-clock, Cost) with the Global Constraints figures and Task 13's measured ones; Task 13's three results with their execution ids; and one line saying the brief's premarket high is out of scope and belongs to the brief spec.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-DATA-001` record (`:513`): append to the Status cell (`:520`) `; flags for prints isolated from their minute in the SPY, QQQ and IWM 1-min bars, written to two new tables by the nightly fetch job under rule isolated-print-v1, with a history run and counts in the bucket manifest ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed; no stored bar is changed and no consumer reads a flag)`; set Last reviewed to the date of the PR's head commit.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-DATA-001` (`:320`): append the PR to its `**PR lineage:**` line, naming spec PR #1988 and issue #1982. Commit both docs and the plan: `docs(product): record the bar misprint flags under FEAT-DATA-001`.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-DATA-001 | DASHBOARD-04 |` row (`:1311`) and no other byte: the new hash, then this change's prose (the `fetch-alphavantage-intraday` job now judges the SPY, QQQ and IWM bars it wrote and writes flags to `intraday_bar_flags` and `intraday_bar_flag_coverage`; its replace clears those two tables for the replaced month and the month on each side; `GET /api/market/data/{ticker}/{date}`, its reader and the bars are unchanged; tests named), then ` Earlier: ` and the earlier prose unchanged. Commit: `docs(site): note the bar flag pass on DASHBOARD-04`.
- [ ] Site note, steps 3 and 4: run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0). If `origin/main` moved, update the branch, re-render and redo the four steps.
- [ ] Render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass).
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports no `[P1]`, `[P2]` or `[P3]` line that `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push; tick each done_when box with its evidence; only then mark the PR ready. Gate files are not touched, so no red-team pass is owed.

## Close-out (not tasks; the owner's steps)

From the spec's Close-out. None is done by the implementer, none is a done_when box, and each, read-only ones included, starts on the owner's own yes.

- **After the merge, in the spec's order with its checks:** (1) `./gcp/deploy.sh apply-schema`; (2) `./gcp/deploy.sh fetchers`, the schema first because the export reads the coverage table; (3) the history dry run, one execution a ticker; (4) the committed history, two executions a ticker (`--flag-bars-to=2020-12`, then from `2021-01`); (5) the first nightly; (6) the manifests' refresh, if wanted; (7) after any later replace, `--flag-bars-from` over the replaced months and one month on each side.
- **For the owner's Monday problem:** after step 5 the previous night's premarket prints carry flags (`session_part` `extended`). Nothing reads them until the brief spec lands; and the same morning's prints are not flagged in the table before 21:00 ET (see "Order" above).
- **After the close-out:** on a `docs/` branch, the DASHBOARD-04 note and this plan's `status: done`; then the consumers' spec (decision 11).
