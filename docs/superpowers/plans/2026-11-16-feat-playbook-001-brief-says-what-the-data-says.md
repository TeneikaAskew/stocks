---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md
branch: feature/feat-playbook-001-brief-says-what-the-data-says
pr: null
status: ready
---

# Premarket brief says what the data says (gamma footer, today's setup, RVOL, premarket high and low, a replay that writes nothing): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are named as the spec names them, B1 to B12 (with B6b, B7a, B7b, B7c and B8b).

**Goal:** The 08:30 ET brief names the gamma snapshot it used, prints the stored TF bias, gives the overview model the candles and withholds an overview that contradicts them, shows one relative volume from `lib`, takes its premarket high and low from confirmed prints, and can be replayed with no write at all.

**Architecture:** Pure functions carry each correction and the tests: `format_gamma_footer`, `format_tf_bias`, `overview_user_text`, `overview_system_prompt`, `overview_conflicts`, `relative_volume`, three extreme rules inside `calculate_premarket_context`, `is_current_pick_rule`, `build_persist_rows`. The job (`gcp/premarket_brief.py`) and the three premarket writers call them. `LEVEL_RULE_VERSION` moves to v4 and every reader of the pick rule goes through one helper, so a stored v3 basis reads as it does today.

**Tech Stack:** Python, pandas, numpy, SQLAlchemy through `gcp.database`, argparse, pytest (`monkeypatch`, `caplog`, `capsys`), `ast` for the two meta tests.

**Spec:** docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md (approved, merged in PR #1993; on `origin/main` 7c74cee94 when this plan was written).

## What is in this plan and what is not

13 tasks, one branch, one PR. The spec's own size list has 12; its item 12 is split here into the evidence (Task 12) and the records (Task 13), and nothing else is added.

In scope: B1, B2, B3, B4, B5, B6, B6b, B7, B7a, B7c, B8, B8b, B9, B10, B11, B12, and B7b in the form its second half states.

- **B7b is closed by its "file does not exist" half.** `git ls-tree origin/main lib/bar_prints.py` printed nothing on 7c74cee94 (run 2026-11-16), so the module is not on main. The spec: "when the file does not exist on the merge base, the PR body says so with the merge base's sha and git ls-tree output, and Design 4 'Order' step 2 stays open for its own spec". Task 6 starts by checking the code branch's real merge base. If the file is there by then, stop and tell the owner: B7b's first half then needs a task this plan does not hold, and it is not improvised.
- **Out of this plan: every RVOL consumer switch (rows 2 to 16 of the spec's Problem 3 table).** The spec stages them: "This PR is stage 1: the one definition lands in `lib` and the brief shows it. No signal consumer, threshold or stored signal column changes here; each switches in its own stage 2 PR with a replay comparison (Design 3)", and "Stage 2, one PR per consumer, each under its own approved spec. Not part of this PR's `done_when`." No task here edits `gcp/signal_monitor.py`, `lib/strategies/`, `lib/signals.py`, `lib/backtest.py`, `lib/trading_analysis.py`, `lib/agents/summarizers.py`, `platform/api/routers/live.py`, `playbook.py` or `config.py`, or `scripts/calibrate_thresholds.py`, and `calculate_rvol`, `calculate_rvol_recent`, `calculate_rvol_vs_baseline` and `calculate_rvol_minute_of_day` keep their formulas.
- **Out of this plan: the spec's Close-out.** Deploy, the 11/16 replay on the job, the market check and the browser proof are the owner's steps after the merge. They are listed at the end and are not tasks.

## Global Constraints

- Base: `origin/main` at or after 7c74cee94. The spec's code references are to `main` 4155a10f and 060c89a0; `git diff --stat 060c89a0 origin/main -- lib gcp tests scripts platform` was empty on 7c74cee94 (run 2026-11-16), so its line numbers hold there. Rerun that diff against the base actually used and re-find any line that moved. Branch `feature/feat-playbook-001-brief-says-what-the-data-says`. This plan is committed alone on `docs/plan-feat-playbook-001-brief-says-what-the-data-says` and merged before the code branch opens.
- **Tests are hermetic (a departure this plan carries).** CI's Run Tests job checks out a single commit with no `origin/main`, so no test may run `git show origin/main:...`, `git diff origin/main` or any other git command against a second ref. Wherever a done_when item says "as on origin/main" or "exactly what they return on origin/main", the test pins a literal: run the unchanged code on the branch before the task's first edit, paste the printed value into the test, and say in the PR body which literals were captured that way. Fixture files are read from `tests/fixtures/`. No test opens a network connection or a database.
- **Production access is asked for once.** The only steps that read production are Task 11 Step 1 (the read-only export) and Task 12 Step 2 (the thin bar count over stored bars). Both are marked "ask the owner once before running". Put both in one question before Task 11 starts, list the exact statements, and run nothing until the owner says yes. Every read goes through `./scripts/db_query_cr.sh` with no `--commit`, or through `gcp.fetchers.export_intraday_bars.read_bars` over the bucket copy. No task runs a deploy, a schema apply, a job execution, `--recompute-premarket`, or a write.
- No silent fallback (CLAUDE.md 3.7). A missing score, label, weight, volume mean, extreme or cutoff is `None`, NaN or the word "unavailable", never 0, 1.0 or a default. New code adds no `except` that returns an empty value.
- Time (CLAUDE.md 3.9): a zone changes only through `lib/eastern_time.py` (`market_date`, `as_eastern_time`, `previous_session`, `eastern_bounds_utc`). `tests/meta/test_timezone_boundaries.py` fails on a new hand-rolled conversion.
- Not changed by this PR (spec Non-goals): `gcp/schema.sql`; rules (a) and (b) of `premarket_print_filter` and their masks; `pm_spike_atr`, `pm_stale_print_atr` and `lib/level_calibration.py`; `calculate_ftfc`, the FTFC weights and the stored `ftfc_score`; the level builder's picks, targets, stops and exit legs; `gcp/deploy.sh`; the insight pipeline; any RVOL consumer.
- Exact values, copied from the spec:
  - Footer text: `Live gamma · HH:MM ET`; `Gamma as of Fri 11/13 15:55 ET`; `Gamma as of Fri 11/13 close`; `(N sessions old)` beyond one session.
  - TF bias: two decimals of the score rounded to two; `format_tf_bias(-0.30 / 0.40)` is `-0.75`; `None` is `unavailable`.
  - Labels in words: 2U up, 2D down, 1 inside and neutral, 3 outside and neutral in the score.
  - Default weights: daily 0.30, weekly 0.10, monthly none (`StratClassifier.DEFAULT_WEIGHTS`, `lib/strat.py:131-140`).
  - `relative_volume(volume, period=20)`: `volume / volume.shift(1).rolling(period, min_periods=period).mean()`, NaN where that mean is not positive or there are fewer than `period` prior bars. IWM to 2026-11-13: 0.7324, where `calculate_rvol` gives 0.7577.
  - Rule names: `two-bars-or-body-v1`, `stale-close-report-v1`, `thin-bar-v1`. Thin bar minimum: 100 shares.
  - `LEVEL_RULE_VERSION = 'feat-strat-001.v4'`; v3 is `'feat-strat-001.v3'`.
  - Flags: `--no-persist`, `BRIEF_NO_PERSIST=true`, `BRIEF_PREMARKET_FROM_BARS=true`. Printed lines: `premarket cutoff unavailable`, `premarket bars unavailable`.
- Capacity (CLAUDE.md Rule 0; spec Design 6), written into the PR body with a test beside each figure:
  - Scheduled brief: one more single-row gamma probe per ticker, 3 more round trips for SPY, QQQ and IWM, 1.5 to 6 s at 0.5 to 2 s a round trip, each probe capped at 10 s (`gcp/premarket_brief.py:114`). Task 1 asserts two statements a ticker.
  - Dry run with bars: at most 330 one-minute bars a ticker; per ticker one bars read and one read of the live `level_basis`, 6 round trips for three tickers, under 12 s. The spec's table says 3; see "Choices" below. Task 10 asserts the count.
  - Premarket fetchers: no new statement.
  - No new job, schedule or table; no new scheduled cost.
- The render step. A task that changes a file under `gcp/`, `lib/` or `scripts/` ends with it, because the generated inventory cites line numbers:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed), and stage whichever of the three docs changed with the code.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. The PR opens as a draft and stays one until every done_when line in its body is ticked with evidence. Every new test has a red then green record in the PR body: failing output before the code, passing output after.
- **Choices this plan makes where the spec leaves one open or does not match the code** (reported to the owner with the plan):
  - B2 says "the read raising propagates as today". Today it does not propagate: `_load_gamma_freshness` catches every exception and returns the `unavailable` record with a warning (`gcp/premarket_brief.py:237-241`). The plan keeps today's behaviour and pins it; the footer is then omitted, as today.
  - `pm_min_extreme_volume` exists nowhere in the code. It becomes a module constant `PM_MIN_EXTREME_VOLUME = 100` in `lib/indicators.py`, not a calibrated per-ticker parameter (the spec changes no calibration).
  - The effective FTFC weights are read through a new read-only property `StratClassifier.ftfc_weights` (a copy of `_default_weights`, `lib/strat.py:147-150`). `calculate_ftfc` is not edited.
  - `fetch_premarket_refresh` does not write `pre_range_atr` today (`_UPSERT_KEYS`, `gcp/fetchers/fetch_premarket_refresh.py:349-350`), yet B8 has it write NULL there for a rejected extreme. The refresh gains the column, overwritten with the snapshot's own value.
  - `_fetch_reach_rates` filters on `LEVEL_RULE_VERSION` for every session (`lib/movement_statement.py:366-368`). For "a v3 session's counts v3 rows only" it takes the session's own version, read from the tracked row, and falls back to the current version when the session has no row (no rung is tracked then).
  - `tests/lib/session_levels_helpers.py:40` stamps `d8_basis` with `LEVEL_RULE_VERSION`, so after the bump that fixture is v4. The two "v3 as on main" tests set `rule_version` to the literal `'feat-strat-001.v3'` on a copy.
  - The dry run's cutoff comes from `lib.strat_levels.read_live_level_basis` (`:2949`), one read a ticker. The brief reads no `premarket_analysis` row in a normal run, so the spec's "the cutoff from the brief rows already read" has no read to reuse.
  - A dry run with no cutoff or no bars keeps the stored snapshot for that ticker and says which line applied; "keeps no recomputed value" is read that way.
  - `--no-persist` wins over `BRIEF_POST_TO_DISCORD=true`: nothing is posted.
  - `format_gamma_footer` returns the plain text; `_build_gamma_footer` keeps the green mark in front of a Live line and the warning mark in front of a line that carries an age, as it does today for its tiers.
  - An EOD chain dated the session date reads `Gamma as of <day> close`, never Live.
  - Database-level read-only sessions for a dry run (Design 5, "where the engine allows it") are not added: whether `gcp.database.get_engine` can open one was not checked by the spec or by this plan. B9's recorder is the proof.

## done_when map

| done_when | What | Task |
|---|---|---|
| B1 | the gamma footer's text | 1 |
| B2 | the newest snapshot wins | 1 |
| B3 | TF bias prints the stored score | 2 |
| B4 | the overview is told the candles and the weights | 3 |
| B5 | the overview cannot contradict the labels | 4 |
| B6 | `relative_volume`, and the brief shows it | 5, 11 (the IWM volumes) |
| B6b | nothing new may be called RVOL | 5 |
| B7 | a premarket extreme must be confirmed | 6 |
| B7a | a stale closing-price report sets no extreme | 6 |
| B7c | a thin bar sets no extreme | 6, 12 (the count) |
| B7b | the misprint rule, or the PR body's statement that its module is not on the merge base | 6 (check), 12 (statement) |
| B8 | the writers record the rules and clear a rejected extreme; the 11/16 session | 7, 11 |
| B8b | v4, v3 read as today, one helper | 8 |
| B9 | a replay that writes nothing | 9 |
| B10 | the dry run recomputes the premarket from bars | 10 |
| B11 | evidence in the PR body | 12 |
| B12 | records, snapshot, audit, gate | 13 |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **A morning with no confirmed extreme reaches the brief.** Task 7 makes the writers store NULL in `pre_high` and `pre_low` with `pre_filter_status` still `ok`. The level builder then gets a snapshot with a VWAP and no extremes. A reader expects a brief with no `PMK_H` or `PMK_L` rung and triggers from the other levels, not a crash and not a `PLAYBOOK_FAILED` row. Task 7.
- **The first v4 morning, read by code that knew v3.** A stored v3 basis given a new premarket snapshot (`SessionLevels.from_basis(v3).with_premarket(snap)`) keeps `rule_version` v3 and its spaced targets, and never falls to the v2 branch. A basis with no version, or `feat-strat-001.v1`, is still not the pick rule. Task 8.
- **What an operator types.** `BRIEF_NO_PERSIST=TRUE` and ` true ` are on; `BRIEF_UPDATE=true` with `--no-persist` exits 2 like `--update`; `BRIEF_POST_TO_DISCORD=true` with `--no-persist` posts nothing; `BRIEF_PREMARKET_FROM_BARS=true` alone exits 2 before any query. Tasks 9 and 10.
- **Volume the rule cannot read.** A premarket bar with NaN volume is not "below 100": it stays a candidate. Volume exactly 100 is not thin; 99 is. A session where `prev_close` is None and one bar is thin still records the thin block. Task 6.
- **Text and numbers at their edges.** `format_tf_bias(float('nan'))` is `unavailable`; `format_tf_bias(0.0)` is `+0.00`. A snapshot timestamp with no zone is read as UTC; one that cannot be parsed gives no footer, not an exception. `overview_conflicts` reads `Weekly`, `WEEKLY` and `IWM's` as it reads `weekly` and `IWM`; a model reply of `None` stays `None` and is not replaced by the deterministic sentence. Tasks 1, 2 and 4.

## File map

| File | Change | Task |
|---|---|---|
| `gcp/premarket_brief.py` | `_load_gamma_freshness` (`:72-241`), `format_gamma_footer` (new), `_build_gamma_footer` (`:1938-1996`), `_fmt_gamma_ts` (`:1920-1935`, removed when unused) | 1 |
| `gcp/premarket_brief.py` | render sites `:2047`, `:2213`; `brief['ftfc_weights']`; RVOL at `:1109-1111` | 2, 3, 5 |
| `gcp/premarket_brief.py` | `build_persist_rows` (from `persist_to_cloud_sql`, `:3598-3956`), `generate_premarket_brief` (`:957`, writes at `:1032` and `:1433-1488`, snapshot at `:1354`), `main` (`:4208-4372`) | 9, 10 |
| `gcp/brief_explanations.py` | `format_tf_bias`, `_tf_bias` (`:141-147`), `_OVERVIEW_PROMPT` (`:161-174`), `explain_overview_setup` (`:177-190`), `overview_user_text`, `overview_system_prompt`, `overview_conflicts`, `deterministic_overview`, `generate_explanations` (`:346`) | 2, 3, 4 |
| `lib/strat.py` | `StratClassifier.ftfc_weights` property (beside `:147-150`) | 3 |
| `lib/indicators.py` | `relative_volume` (beside `:215-218`); the three rules in `calculate_premarket_context` (`:523-657`, extremes at `:634-638`); `premarket_rule_record` | 5, 6 |
| `gcp/fetchers/fetch_market_data.py` | `premarket_snapshot` (`:380-445`), the price-column loop (`:598-606`) | 7 |
| `gcp/fetchers/fetch_premarket_refresh.py` | the snapshot (`:247-268`), `upsert_premarket` (`:302-345`), `_UPSERT_KEYS` (`:349-350`), `_upsert_premarket_sql` (`:371-390`) | 7 |
| `gcp/backfill_ticker.py` | the premarket block (`:516-541`) | 7 |
| `lib/strat_levels.py` | `LEVEL_RULE_V3`, `LEVEL_RULE_VERSION` (`:1516`), `is_current_pick_rule`, `from_basis` (`:1968-1969`), `_assemble` (`:2434`) | 8 |
| `lib/movement_statement.py` | `_fetch_reach_rates` (`:352-368`), `_new_rule_mark` (`:495-499`), the call order (`:1033-1035`) | 8 |
| `gcp/premarket_playbook_resolver.py` | `plan_inputs` (`:599-611`) | 8 |
| `tests/gcp/test_premarket_brief.py` | `TestGammaFooter` (new), `TestTfBiasAndFtfcRender` (`:3247`), `test_brief_rvol_is_relative_volume`; changed expectations in `TestBuildGammaFooter` (`:2824`) and `TestFmtGammaTs` (`:2922`) | 1, 2, 5 |
| `tests/gcp/test_brief_overview_text.py` | new | 3, 4 |
| `tests/lib/test_indicators.py` | `TestRelativeVolume` (new) | 5, 11 |
| `tests/meta/test_one_rvol_definition.py` | new | 5 |
| `tests/lib/test_premarket_print_filter.py` | `TestConfirmedExtremes`, `TestThinBar`, `TestStaleCloseReport`, `TestSession20261116`; changed expectations | 6, 11 |
| `tests/gcp/test_premarket_filter_params.py` | the confirmed block, `test_writers_clear_rejected_extremes` | 7 |
| `tests/lib/test_movement_statement.py`, `tests/lib/test_strat_levels.py`, `tests/gcp/test_premarket_playbook_resolver.py`, `tests/meta/test_level_rule_version_readers.py` (new) | B8b | 8 |
| `tests/gcp/test_premarket_brief_no_discord.py`, `tests/gcp/brief_dry_run_helpers.py` (new) | `TestNoPersist`, `TestPremarketFromBars`, the recorder | 9, 10 |
| `tests/fixtures/premarket_2026_11_16/` | new: the exported files and `sources.json` | 11 |
| `tests/gcp/run_brief_2026_11_16.py` | new: the local dry run of B11 | 12 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 1 to 10 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 13 |

---

### Task 1: The gamma probe takes the newest snapshot and the footer names it

Spec: Problem 1; Design 1. Closes B1 and B2.

**Files:**
- Modify: `gcp/premarket_brief.py` (`_load_gamma_freshness` `:72-241`, `_build_gamma_footer` `:1938-1996`, `_fmt_gamma_ts` `:1920-1935`)
- Test: `tests/gcp/test_premarket_brief.py` (new class `TestGammaFooter`; `TestBuildGammaFooter` `:2824` and `TestFmtGammaTs` `:2922` change)

**Interfaces:**
- Consumes: `lib.eastern_time.previous_session`, `market_date`, `as_eastern_time`, `localize_assuming_utc`.
- Produces:
  - `format_gamma_footer(snapshot_ts: datetime | str, market_session: str | None, session_date: date) -> str`, pure. `market_session` of `'REALTIME'` is a live chain; `'EOD'` or `None` is a close.
  - `_load_gamma_freshness(ticker, as_of) -> dict` keeps its keys (`data_source`, `snapshot_ts`, `snapshot_date`, `days_behind`) and gains `market_session`. `days_behind` is the number of `previous_session` steps from `as_of` back to the snapshot's Eastern date (0 on the same date, 1 for Friday read on Monday). `data_source` is `realtime` when the winning row is REALTIME, otherwise `classify_gamma_freshness(days_behind)` as today.
  - `brief['tickers'][T]['gamma_market_session']`, set where `gamma_data_source` is set.

- [ ] **Step 1: Write the failing tests** in `TestGammaFooter`:
  - `test_same_session_snapshot_is_live`: `format_gamma_footer('2026-11-16T14:35:00+00:00', 'REALTIME', date(2026, 11, 16)) == 'Live gamma · 09:35 ET'`.
  - `test_earlier_realtime_snapshot_names_its_day`: `('2026-11-13T20:55:30+00:00', 'REALTIME', date(2026, 11, 16))` gives `'Gamma as of Fri 11/13 15:55 ET'`, and `'Live' not in` the result.
  - `test_eod_snapshot_reads_close`: `('2026-11-13T23:00:00+00:00', 'EOD', date(2026, 11, 16))` gives `'Gamma as of Fri 11/13 close'`; the same with `market_session=None`.
  - `test_older_snapshot_gives_its_age_in_sessions`: `('2026-11-12T23:00:00+00:00', 'EOD', date(2026, 11, 16))` gives `'Gamma as of Thu 11/12 close (2 sessions old)'`.
  - `test_a_holiday_is_not_a_missed_session`: Wednesday `'2026-11-25T23:00:00+00:00'`, `'EOD'`, session Friday `date(2026, 11, 27)` (Thanksgiving between) gives `'Gamma as of Wed 11/25 close'` with no age.
  - `test_probe_takes_the_newest_snapshot`: the two probe statements answered by a stand-in for `gcp.database.get_engine` and `pd.read_sql` that answers by whether the statement text holds `'REALTIME'`: a REALTIME row at `2026-11-13 20:55:30Z` and an EOD row at `2026-11-13 23:00:00Z`, `as_of=date(2026, 11, 16)`. Assert `market_session == 'EOD'`, `snapshot_ts` is the EOD instant, `days_behind == 1`; with the EOD row absent the REALTIME row returns with `days_behind == 1`; both statements were issued in each case (two a ticker, the Capacity figure).
  - `test_probe_failure_is_unavailable_as_today`: the read raising `RuntimeError` returns `{'data_source': 'unavailable', 'snapshot_ts': None, 'snapshot_date': None, 'days_behind': None}` and logs one warning (the behaviour of `:237-241`, pinned; see "Choices").
  - `test_footer_describes_the_oldest_snapshot`: a brief of three tickers, two on the 11/13 EOD chain and one on a 11/12 chain, renders the 11/12 line; every ticker `unavailable` renders `None`.
  - Review Focus: `test_naive_timestamp_is_utc` (`'2026-11-13 20:55:30'` reads as 15:55 ET) and `test_unparseable_timestamp_gives_no_footer` (`_build_gamma_footer` returns `None`, no exception).
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_brief.py::TestGammaFooter -q` (expect FAIL: `format_gamma_footer` not defined).
- [ ] **Step 3: Implement.** Both single-row probes run on the one connection under the existing `SET LOCAL statement_timeout`; the row with the greater `snapshot_ts` wins. `_build_gamma_footer` picks the ticker with the oldest `gamma_snapshot_ts` among those with a snapshot and calls `format_gamma_footer`. The snapshot's Eastern date comes from `lib.eastern_time.market_date` of its instant.
- [ ] **Step 4: Update** `TestBuildGammaFooter` and `TestFmtGammaTs` to the new text. List each changed assertion, old and new, for the PR body. A test of `_fmt_gamma_ts` goes when the function goes.
- [ ] **Step 5: Run:** `python3 -m pytest tests/gcp/test_premarket_brief.py tests/gcp/test_premarket_brief_late_slot.py tests/gcp/test_strat_snapshot_parity.py -q` (expect all passed), then the render step.
- [ ] **Step 6: Commit:** `fix(brief): name the gamma snapshot the footer describes`

### Task 2: TF bias prints the stored score

Spec: Problem 2; Design 2 (first bullet); decision 1. Closes B3.

**Files:**
- Modify: `gcp/brief_explanations.py` (`_tf_bias`, `:141-147`), `gcp/premarket_brief.py` (`:2047`, `:2213`)
- Test: `tests/gcp/test_premarket_brief.py` (`TestTfBiasAndFtfcRender`, `:3247`)

**Interfaces:**
- Produces: `format_tf_bias(score: float | None) -> str` in `gcp/brief_explanations.py`: `'unavailable'` for `None` or NaN, otherwise `f"{round(score, 2):+.2f}"`.

- [ ] **Step 1: Write the failing test** `TestTfBiasAndFtfcRender::test_score_prints_two_decimals`:
  - `format_tf_bias(-0.30 / 0.40) == '-0.75'`; `format_tf_bias(None) == 'unavailable'`; `format_tf_bias(0.75) == '+0.75'`.
  - a brief dict with `ftfc_score = -0.30 / 0.40`, `ftfc_direction = 'bearish'`: `_build_overview_embed` holds `'IWM: bearish (-0.75)'`, the ticker field from `_build_ticker_fields` holds `'TF bias: -0.75 (bearish)'`, and `brief_explanations._tf_bias(d) == '-0.75 (bearish)'`.
  - an `ast` walk of the two modules finds no `+.1f` format applied to `ftfc_score`.
  - Review Focus: `format_tf_bias(float('nan')) == 'unavailable'`; `format_tf_bias(0.0) == '+0.00'`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender -q` (expect FAIL: `format_tf_bias` not defined; on the unchanged code the three sites print `-0.7`).
- [ ] **Step 3: Implement** the function and make the three sites call it.
- [ ] **Step 4: Run** the same command plus `tests/gcp/test_premarket_brief.py -q`; update each assertion in the file that expected one decimal and list it for the PR body (expect all passed). Then the render step.
- [ ] **Step 5: Commit:** `fix(brief): print the TF bias to the two decimals it is stored with`

### Task 3: The overview is sent the candles and the weights in force

Spec: Problem 2; Design 2 (second and third bullets); decision 2. Closes B4.

**Files:**
- Modify: `lib/strat.py` (property beside `:147-150`), `gcp/premarket_brief.py` (`generate_premarket_brief`, where `strat` is built, `:984`), `gcp/brief_explanations.py` (`_OVERVIEW_PROMPT` `:161-174`, `explain_overview_setup` `:177-190`, `generate_explanations` `:346`)
- Create: `tests/gcp/test_brief_overview_text.py`

**Interfaces:**
- Produces:
  - `StratClassifier.ftfc_weights -> dict[str, float]`: a copy of the weights the classifier scores with.
  - `brief['ftfc_weights']`: that dict, set once in `generate_premarket_brief`.
  - `overview_user_text(tickers: dict[str, dict]) -> str | None`, pure: one line a ticker; `None` when no ticker has data.
  - `overview_system_prompt(weights: dict[str, float] | None) -> str`, pure.
  - `explain_overview_setup(tickers: dict[str, dict], weights: dict[str, float] | None = None) -> str | None`; `generate_explanations` passes `brief.get('ftfc_weights')`.
  - Constants `LABEL_WORDS = {'2U': 'up', '2D': 'down', '1': 'inside and neutral', '3': 'outside and neutral in the score'}` and `TIMEFRAME_WORDS = {'1d': 'daily', '1w': 'weekly', '1mo': 'monthly'}`, which Task 4 reads.

- [ ] **Step 1: Write the failing tests** (no model is called; the tests read the two pure functions):
  - `test_user_text_holds_each_candle_with_its_meaning`: for IWM with `ftfc_labels {'1d': '2D', '1w': '1', '1mo': '2U'}`, `macd_cross 'Bullish'`, `ftfc_score -0.75`, the IWM line holds `'daily 2D (down)'`, `'weekly 1 (inside and neutral)'`, `'monthly 2U (up)'`, `'MACD cross Bullish'` and `'TF bias -0.75 (bearish)'`.
  - `test_default_weights_are_read_not_typed`: `overview_system_prompt(StratClassifier().ftfc_weights)` holds `'daily 0.30'`, `'weekly 0.10'` and `'monthly none'`; and with `DEFAULT_WEIGHTS` monkeypatched so `'1d'` is 0.25 the prompt holds `'daily 0.25'` (the number is not in the prompt's source).
  - `test_configured_monthly_weight_is_named`: `StratClassifier(strat_config=StratConfig(ftfc_weights={'1d': 0.30, '1w': 0.10, '1mo': 0.20})).ftfc_weights` gives a prompt holding `'monthly 0.20'` and not `'monthly none'`.
  - `test_prompt_says_inside_and_outside_add_nothing`: the prompt holds a sentence stating that an inside (1) or outside (3) bar adds nothing to the score, and one stating that the score's sign is not a statement about any one timeframe; it no longer holds `'a weighted vote of daily and weekly candle types'`.
  - `test_missing_labels_are_unavailable`: a ticker with no `ftfc_labels` key gives `'candles unavailable'` and no label; a ticker with `{'1d': '2D'}` only gives `'weekly unavailable'` and `'monthly unavailable'`.
  - `test_weights_unknown_is_said`: `overview_system_prompt(None)` holds `'weights unavailable'` and no number.
  - `test_brief_carries_the_weights`: through the run helper `tests/gcp/test_strat_snapshot_parity.py` uses (`:55-67`), `generate_premarket_brief(cfg=cfg)['ftfc_weights'] == StratClassifier(strat_config=cfg.strat).ftfc_weights`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_brief_overview_text.py -q` (expect FAIL: `overview_user_text` not defined).
- [ ] **Step 3: Implement.** The prompt's weight sentence is built from the dict over the timeframes in `TIMEFRAME_WORDS`; a timeframe absent from the dict, or with weight 0, reads `none`. On the user-text line that still reads `d.get('price', 0)` and `d.get('rsi', 0)` (`:185`), add `# AUDIT-2026-05-13: silent fallback` with why it is reachable; do not extend it.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/gcp/test_premarket_brief.py tests/lib/test_strat.py -q` (expect all passed), then the render step.
- [ ] **Step 5: Commit:** `fix(brief): send the overview each candle and the weights the score used`

### Task 4: An overview that contradicts the labels is withheld

Spec: Design 2 (fourth bullet); decision 8 (the review fix to B5). Closes B5.

**Files:**
- Modify: `gcp/brief_explanations.py`
- Test: `tests/gcp/test_brief_overview_text.py` (class `TestOverviewCheck`)

**Interfaces:**
- Consumes: `LABEL_WORDS`, `TIMEFRAME_WORDS`, `format_tf_bias` (Tasks 2 and 3).
- Produces:
  - `overview_conflicts(text: str, tickers: dict[str, dict]) -> list[dict]`, pure. Each conflict is `{'timeframe': 'daily' | 'weekly' | 'monthly', 'claim': '2U' | '2D', 'tickers': [names that do not hold it], 'clause': str}`. An empty list is no conflict.
  - `deterministic_overview(tickers: dict[str, dict]) -> str`, pure: one sentence a ticker in the spec's form, `'IWM: daily 2D (down), weekly 1 (inside), monthly 2U (up), TF bias -0.75.'`, joined by one space.
  - `explain_overview_setup` returns `deterministic_overview(tickers)` and logs the withheld text at WARNING, in a line starting `overview withheld:`, when `overview_conflicts` is not empty. No second model call.

- [ ] **Step 1: Write the failing tests.** Three tickers SPY, QQQ, IWM unless a case says otherwise; weekly labels given per case.
  - `'strong bearish alignment on the daily and weekly'` with every weekly `'1'` and every daily `'2D'`: one conflict, `timeframe 'weekly'`, `claim '2D'`, `tickers ['IWM', 'QQQ', 'SPY']` in sorted order.
  - the same sentence with every weekly `'2D'`: `[]`.
  - `'the monthly is bullish'` with no `'2U'` monthly: a conflict naming monthly.
  - `'Volume was light into the close.'`: `[]`.
  - `'all three names are bearish on the weekly'` with weekly `2D`, `1`, `1` for SPY, QQQ, IWM: one conflict whose `tickers` are `['IWM', 'QQQ']`; `[]` when all three are `2D`.
  - `'SPY and QQQ are bearish on the daily'` with SPY `2D` and QQQ `2U`: one conflict, `tickers ['QQQ']`.
  - `'one of the three is bearish on the weekly'` with weekly `2D`, `1`, `1`: `[]`; with no `2D`: a conflict.
  - `test_conflict_returns_the_deterministic_sentence`: `_call` monkeypatched to return the first sentence above; `explain_overview_setup` returns `deterministic_overview(tickers)`, the IWM part reads exactly `'IWM: daily 2D (down), weekly 1 (inside), monthly 2U (up), TF bias -0.75.'`, `caplog` holds one `overview withheld:` line with the model's text, and `_call` was awaited once.
  - Review Focus: `'Weekly'`, `'WEEKLY'` and `"IWM's weekly is bearish"` are read as `weekly` and `IWM`; `_call` returning `None` makes `explain_overview_setup` return `None`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_brief_overview_text.py::TestOverviewCheck -q` (expect FAIL: `overview_conflicts` not defined).
- [ ] **Step 3: Implement.** Clauses split on `.`, `;`, `,` and the words `but`, `while`, `whereas`. Direction words: `bearish`, `down`, `lower` claim `2D`; `bullish`, `up`, `higher` claim `2U`. A clause with a direction word and one or more timeframe words makes one claim per timeframe. The tickers a clause describes are the brief tickers it names, else all of them. Partial quantifiers, matched as whole words: `one of`, `some`, `two of three`, `two of the three`, `most`; such a clause needs at least one ticker holding the claim (two for the two forms of "two of").
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_brief_overview_text.py tests/gcp/test_premarket_brief.py -q` (expect all passed), then the render step.
- [ ] **Step 5: Commit:** `fix(brief): withhold an overview that contradicts the candle labels`

### Task 5: One relative volume in `lib`, shown by the brief, and a list that only shrinks

Spec: Problem 3; Design 3, "Stage 1, this PR"; decision 3. Advances B6 (closed in Task 11 by the IWM volumes); closes B6b.

**Files:**
- Modify: `lib/indicators.py` (new function beside `:215-218`), `gcp/premarket_brief.py` (`:1109-1111`)
- Test: `tests/lib/test_indicators.py` (class `TestRelativeVolume`), `tests/gcp/test_premarket_brief.py` (`test_brief_rvol_is_relative_volume`)
- Create: `tests/meta/test_one_rvol_definition.py`

**Interfaces:**
- Produces: `relative_volume(volume: pd.Series, period: int = 20) -> pd.Series` in `lib/indicators.py`. Its docstring states the owner's definition and that it is the only computation in the codebase that may be called relative volume or RVOL.

- [ ] **Step 1: Capture the pins.** Before any edit, on a 30-value volume series and a matching intraday `times` series written in the test, print what `calculate_rvol`, `calculate_rvol_recent`, `calculate_rvol_vs_baseline` (with a baseline dict written in the test) and `calculate_rvol_minute_of_day` return, and paste the four arrays into the test as literals.
- [ ] **Step 2: Write the failing tests:**
  - `TestRelativeVolume::test_definition`: for a 25-value series, positions 0 to 19 are NaN and position 20 equals `volume[20] / mean(volume[0:20])`; the bar's own volume is not in its mean (doubling `volume[20]` doubles the result at 20 and leaves the mean unchanged).
  - `test_fewer_than_period_prior_bars_is_nan`: a 20-value series is all NaN; never 1.0 and never 0.
  - `test_non_positive_mean_is_nan`: 20 zeros then 5: NaN at position 20.
  - `test_other_volume_ratios_are_unchanged`: the four functions return the Step 1 literals (`np.testing.assert_allclose`, `rtol=0`, `atol=0`, NaN equal).
  - `test_brief_rvol_is_relative_volume` (module level, in `tests/gcp/test_premarket_brief.py`): through the same run helper as Task 3, a ticker's `rvol` equals `relative_volume(df['Volume'], 20).iloc[-1]` of the frame the brief used, and differs from the old `Volume / rolling(20).mean()` value; with a frame of 15 rows `rvol is None` and the overview line holds no `'RVOL'`.
  - `tests/meta/test_one_rvol_definition.py::test_only_listed_names_are_called_rvol`: an `ast` scan of every `.py` file under `lib`, `gcp`, `platform/api` and `scripts` collects `(file, name)` for each function definition and each assignment target, subscript string key, dict literal key and keyword argument name matching `rvol` or `vol_ratio` in any letter case. Each is `lib/indicators.py::relative_volume`, is in `READS_THE_DEFINITION` (the brief's `rvol`), or is in `STAGE_2`, a dict of `(file, name)` to the row number of the spec's Problem 3 table. An unlisted name fails with its file and line; a `STAGE_2` entry the scan no longer finds fails with "take it off the list".
- [ ] **Step 3: Run:** `python3 -m pytest tests/lib/test_indicators.py::TestRelativeVolume tests/meta/test_one_rvol_definition.py "tests/gcp/test_premarket_brief.py::test_brief_rvol_is_relative_volume" -q` (expect FAIL: `relative_volume` not defined).
- [ ] **Step 4: Implement** `relative_volume` with the exact expression in Global Constraints, and the brief's call: `rvol` is the last value, `None` when it is NaN. Line `:2029` is unchanged.
- [ ] **Step 5: Fill `STAGE_2`** from the scan's own output, giving each entry its table row. An entry that fits no row of the table is not listed: report it to the owner with its file and line, since the spec's table would be incomplete.
- [ ] **Step 6: The IWM case.** `TestRelativeVolume::test_iwm_to_2026_11_13`: the 21 IWM daily volumes to 2026-11-13, written in the test, give `relative_volume(v, 20).iloc[-1] == pytest.approx(0.7324, abs=5e-5)` and `calculate_rvol(v, 20).iloc[-1] == pytest.approx(0.7577, abs=5e-5)`, with the last volume 17,722,264. The 21 values come from Task 11's export. If the owner has not said yes yet, leave this one case out, finish the task, and add it in Task 11; B6 is not ticked before it passes.
- [ ] **Step 7: Run** the Step 3 command and `python3 -m pytest tests/gcp/test_premarket_brief.py tests/lib/test_indicators.py -q` (expect all passed), then the render step.
- [ ] **Step 8: Commit:** `feat(indicators): add the one relative volume and show it in the brief`

### Task 6: A premarket extreme must be confirmed, by a bar that is not thin, and not by a closing-price report

Spec: Problem 4; Design 4 (the five bullets before "Order"); decisions 5 and 9. Closes B7, B7a, B7c; checks B7b.

**Files:**
- Modify: `lib/indicators.py` (`calculate_premarket_context`, `:523-657`; the extremes at `:634-638`)
- Test: `tests/lib/test_premarket_print_filter.py` (classes `TestStaleCloseReport`, `TestThinBar`, `TestConfirmedExtremes`)

**Interfaces:**
- Consumes: `premarket_print_filter` (`:661-713`, unchanged); `lib.strat_levels.price_cents`.
- Produces:
  - Constants `PM_MIN_EXTREME_VOLUME = 100`, `CONFIRMED_RULE = 'two-bars-or-body-v1'`, `STALE_CLOSE_RULE = 'stale-close-report-v1'`, `THIN_BAR_RULE = 'thin-bar-v1'`.
  - `calculate_premarket_context(...)` keeps its signature and gains two result keys:
    - `confirmed`: `{'rule', 'raw_high', 'raw_low', 'high_bars_above', 'low_bars_below', 'stale_close_reports', 'reason'}`. `raw_high` and `raw_low` are what the unchanged code returns (the maximum and minimum after rules (a) and (b)). `high_bars_above` counts candidate bars whose surviving high is above `pre_high`; `low_bars_below` mirrors it. `stale_close_reports` is `{'rule', 'high', 'low', 'prior_close'}`, or `None` when `prev_close` is None. `reason` is `None`, `'all_bars_thin'` or `'unconfirmed'`.
    - `thin`: `{'rule', 'min_volume', 'bars_excluded'}`.
  - `premarket_rule_record(pm: dict) -> dict` returning `{'confirmed': pm['confirmed'], 'thin': pm['thin']}`, which Task 7's writers merge into `pre_filter_params`.

- [ ] **Step 0: Check the merge base for B7b.** Run `git ls-tree $(git merge-base HEAD origin/main) lib/bar_prints.py` and keep the sha and the output for Task 12. Empty output: go on. Any output: stop and tell the owner (see "What is in this plan").
- [ ] **Step 1: Write the failing tests.** A helper `bars(rows)` builds aligned series from `(HH:MM, open, high, low, close, volume)` on one Eastern morning; a helper `mirror(rows, about)` reflects prices about a level and swaps high with low, so each case runs for the high side and the low side from one parametrised test.
  - `TestStaleCloseReport` (ATR `None`, both thresholds `None`, so rules (a) and (b) do not run; `prev_close=277.54`):
    - a bar with open 276.50, close 276.60, high 277.54 among bars trading 276.2 to 276.6 does not set `pre_high`; the bar still counts through its body; `confirmed['stale_close_reports'] == {'rule': 'stale-close-report-v1', 'high': 1, 'low': 0, 'prior_close': 277.54}`.
    - the mirrored bar of a gap-up morning (open 279.10, close 279.00, low 277.54) does not set `pre_low`, with `{'high': 0, 'low': 1}`.
    - a bar that opens or closes at 277.54 keeps that extreme; a high of 277.55 or of 277.53 is kept.
    - `prev_close=None`: nothing is dropped and `confirmed['stale_close_reports'] is None`.
    - `pre_vwap`, `pre_volume` and `gap_pct` equal literals captured from the unchanged code on the same bars (hermetic pin).
  - `TestThinBar`:
    - the 2026-11-16 IWM 08:05 bar (open 276.4801, high 278.92, low 276.4801, close 278.92, volume 1) among bars trading 276.26 to 276.35 at volume 5,000: `pre_high` is not 278.92 and is at most 276.35.
    - a bar of volume 0 with all four prices 277.54 does not set it; the 08:05 bar at volume 100 does set `pre_high == 278.92`.
    - every surviving bar thin: `pre_high is None`, `pre_low is None`, `pre_range_atr is None`, `confirmed['reason'] == 'all_bars_thin'`.
    - `thin == {'rule': 'thin-bar-v1', 'min_volume': 100, 'bars_excluded': N}` with N written per case; `pre_vwap` and `gap_pct` equal the captured literals.
    - Review Focus: a NaN-volume bar stays a candidate; volume 99 is thin and 100 is not; `prev_close=None` with one thin bar still records `thin`.
  - `TestConfirmedExtremes` (after (a), (b), the stale rule and the thin rule):
    - one bar whose high stands alone above every other high and every open and close does not set `pre_high`; `pre_high` equals the greater of the second-highest surviving high and the highest surviving open or close; `confirmed['rule'] == 'two-bars-or-body-v1'`, `raw_high` is the lone high, `high_bars_above == 1`.
    - two bars at the same high set it, with `high_bars_above == 0`.
    - a bar that opens or closes at its high sets it when its volume is 100 or more.
    - one surviving bar: `pre_high == max(open, close)` and `pre_low == min(open, close)`.
    - one surviving bar whose open and close rule (a) dropped: `pre_high is None`, `confirmed['reason'] == 'unconfirmed'`.
    - the rule (a) and (b) masks from `premarket_print_filter` on the same bars, `pre_vwap` and `gap_pct` equal the captured literals.
- [ ] **Step 2: Run:** `python3 -m pytest tests/lib/test_premarket_print_filter.py -q -k "StaleCloseReport or ThinBar or ConfirmedExtremes"` (expect FAIL: `KeyError: 'confirmed'`; on the unchanged code a 277.54 high with the filter not running sets `pre_high`).
- [ ] **Step 3: Implement,** in this order inside `calculate_premarket_context`, after the `premarket_print_filter` call and before the VWAP block, which is not edited:
  1. Stale closing-price report: where `prev_close` is positive, a surviving high equal to it to the cent, on a bar whose own open and close are both not equal to it to the cent, is dropped from the candidates and counted; the low the same.
  2. Thin bar: a bar whose volume is a number below `PM_MIN_EXTREME_VOLUME` gives none of its four prices to the candidates.
  3. Confirmed: over the candidate bars, `pre_high = max(second-highest surviving high, highest surviving open or close)`, taking only the terms that exist; `pre_low` mirrors it. No term: `None`, with the reason.
  `pre_range_atr` is computed from the new extremes by the existing lines.
- [ ] **Step 4: Run** the Step 2 command (expect all passed), then `python3 -m pytest tests/lib/test_premarket_print_filter.py tests/gcp/test_premarket_filter_callers.py tests/lib/test_brief_planner_parity.py -q`. For each test that now fails because it asserted a high or low set by one lone wick or by a thin bar: read the fixture bar that set the old value, confirm the rule that rejects it, change the expectation, and record test, old value, new value and reason for B11. A failure for any other reason is a defect in Step 3, not a changed expectation.
- [ ] **Step 5: Run** `python3 -m pytest tests/lib tests/gcp -q -k "premarket or level or strat"` (expect all passed), then the render step.
- [ ] **Step 6: Commit:** `fix(levels): take the premarket high and low from confirmed prints`

### Task 7: The three writers record the rules and clear a rejected extreme

Spec: Design 4 (last bullet before "Order"); decision 8. Advances B8 (its first and third parts; Task 11 closes it).

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py` (`premarket_snapshot` `:380-445`; the loop at `:598-606`), `gcp/fetchers/fetch_premarket_refresh.py` (`:247-268`, `:302-345`, `:349-350`, `:371-390`), `gcp/backfill_ticker.py` (`:516-541`)
- Test: `tests/gcp/test_premarket_filter_params.py`

**Interfaces:**
- Consumes: `premarket_rule_record` (Task 6).
- Produces: in each writer, `pre_filter_params` is the threshold record of `premarket_filter_inputs` merged with `premarket_rule_record(pm)`; when that record is `None` (parameters unreadable) it holds the two rule blocks alone. `pre_high`, `pre_low` and `pre_range_atr` are written as computed, `None` included, whenever a snapshot was computed.

- [ ] **Step 1: Write the failing tests,** parametrised over the three writers. The file's `writer` parametrisation (`:160`) covers the nightly (`_nightly_row`) and the refresh (`_refresh_row`); add a `_backfill_row` helper beside them that runs `gcp/backfill_ticker.py`'s premarket block against the same stand-in:
  - `test_written_row_holds_the_rule_blocks`: the written `pre_filter_params` holds `confirmed` with `rule 'two-bars-or-body-v1'` and a `stale_close_reports` block, and `thin` with `rule 'thin-bar-v1'`, beside the existing `pm_spike_atr` and `pm_stale_print_atr` records.
  - `test_writers_clear_rejected_extremes`: starting from a stored `market_data_daily` row holding `pre_high`, `pre_low` and `pre_range_atr`, recompute (a) a session whose bars are all thin and (b) a session whose only extreme is unconfirmed. The row handed to the write holds `None` for the three columns, and the statement the refresh issues sets `pre_high`, `pre_low` and `pre_range_atr` from `EXCLUDED` with no `COALESCE`; `pre_filter_params['confirmed']['reason']` is `'all_bars_thin'` or `'unconfirmed'`.
  - `test_a_writer_that_could_not_compute_leaves_the_row`: no bars fetched, and a vendor error, each issue no write of the three columns.
  - `test_refresh_keeps_a_row_with_only_a_vwap`: a snapshot with `pre_high` and `pre_low` `None` and a `pre_vwap` is still written by `upsert_premarket` (it passes the `useful` filter at `:321-323`).
  - `test_schema_is_unchanged`: `gcp/schema.sql` still declares `pre_filter_params` as JSONB and `pre_range_atr` (`:1756`); its sha256 equals a literal captured before the task.
  - Review Focus, `test_null_extremes_build_levels_without_premarket_rungs`: a session snapshot with `pre_filter_status 'ok'`, a `pre_vwap`, and `pre_high` and `pre_low` `None`, through `build_session_levels`, gives a result whose ladder has no `PMK_H` and no `PMK_L` rung and raises nothing; and through the brief's run helper the ticker's status is not `PLAYBOOK_FAILED`. If this fails, the failure is a finding for the owner before the task goes on: the spec did not read what the builder does with a snapshot that has no extremes.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_filter_params.py -q` (expect FAIL: `'confirmed'` not in the params; the stored price is kept by the `None` skip at `fetch_market_data.py:602-604`, the `COALESCE` at `fetch_premarket_refresh.py:381-382` and the skip at `backfill_ticker.py:526-533`).
- [ ] **Step 3: Implement.** Nightly: `pre_high`, `pre_low` and `pre_range_atr` are set from the snapshot even when `None`; `pre_vwap`, `pre_volume` and `gap_pct` keep the not-`None` rule. Refresh: `pre_range_atr` joins the snapshot and `_UPSERT_KEYS`; `pre_high`, `pre_low` and `pre_range_atr` join the overwrite set; `pre_vwap`, `pre_volume` and `gap_pct` keep `COALESCE`. Backfill: the same three keys are set when `pm['bar_count'] > 0`.
- [ ] **Step 4: Run** the same command and `python3 -m pytest tests/gcp/test_premarket_filter_callers.py tests/gcp -q -k "premarket or recompute or backfill"` (expect all passed; a changed expectation is recorded for B11 as in Task 6), then the render step.
- [ ] **Step 5: Commit:** `fix(fetchers): record the extreme rules and clear a rejected premarket extreme`

### Task 8: The level rule is v4, and v3 reads as it does today

Spec: Design 4, "The rule's version (B8b)"; decisions 7 and 8. Closes B8b.

**Files:**
- Modify: `lib/strat_levels.py` (`:1515-1516`, `:1968-1969`, `:2434`), `lib/movement_statement.py` (`:352-368`, `:495-499`, `:1033-1035`), `gcp/premarket_playbook_resolver.py` (`:599-611`)
- Test: `tests/lib/test_movement_statement.py`, `tests/lib/test_strat_levels.py`, `tests/gcp/test_premarket_playbook_resolver.py`
- Create: `tests/meta/test_level_rule_version_readers.py`

**Interfaces:**
- Produces:
  - `LEVEL_RULE_V3 = 'feat-strat-001.v3'`, `LEVEL_RULE_VERSION = 'feat-strat-001.v4'`, `PICK_RULE_VERSIONS = (LEVEL_RULE_V3, LEVEL_RULE_VERSION)`.
  - `is_current_pick_rule(version) -> bool`: True for a member of `PICK_RULE_VERSIONS`, False for anything else, `None` included.
  - `SessionLevels.from_basis` keeps the basis's own `rule_version` when `is_current_pick_rule` is True, else `LEVEL_RULE_V2`. `_assemble` keeps `base.rule_version` when it is v2 or a pick-rule version, else `LEVEL_RULE_VERSION`.
  - `_fetch_reach_rates(ticker: str, side: str, query_fn, rule_version: str | None = None) -> dict`: the population is rows of exactly `rule_version`, defaulting to `LEVEL_RULE_VERSION`.
  - `_fetch_tracked_levels` adds `rule_version` (the session row's `level_basis.rule_version`, or `None`) to its OK record; `assemble_movement_statement` reads the tracked levels first and passes that version to both reach-rate calls.

- [ ] **Step 1: Capture the pins.** Before any edit, with `d8_basis()` from `tests/lib/session_levels_helpers.py` (v3 on the unchanged code): print the picks of `SessionLevels.from_basis(basis)` for both sides (trigger, stop, targets, gate targets, plan), and `plan_inputs('calls', row, basis, policy_fn)` and `plan_inputs('puts', ...)` as the existing test at `tests/gcp/test_premarket_playbook_resolver.py:913-928` calls them. Paste them as literals.
- [ ] **Step 2: Write the failing tests:**
  - `tests/lib/test_strat_levels.py::test_v3_basis_rebuilds_as_on_main`: `d8_basis()` with `rule_version` set to `'feat-strat-001.v3'` gives the Step 1 picks, and the result's `rule_version` is `'feat-strat-001.v3'`. Beside it, a new build's basis records `'feat-strat-001.v4'`.
  - `tests/lib/test_movement_statement.py::test_reach_rates_do_not_mix_rule_versions`: a `query_fn` stand-in holding resolved rows of v3 and of v4 that filters on the bound `rule_version`: a v4 session's rung takes its rate from v4 rows only, a v3 session's from v3 rows only; the bound value is the session row's own version in each case; the SQL still holds `level_basis->>'rule_version' = :rule_version`.
  - `tests/lib/test_movement_statement.py::test_v3_trigger_on_the_reference_cent_keeps_its_slot`: a stored v3 row whose calls trigger equals its reference price to the cent, with `cleared_above` on that cent, still tracks that price as the trigger and the next rung as T1; `_new_rule_mark(basis, 'calls')` returns the mark for v3 and for v4 and `None` for v2 and for no basis.
  - `tests/gcp/test_premarket_playbook_resolver.py::test_v3_plan_resolves_as_on_main`: `plan_inputs` on the v3 copy of `d8_basis` returns the Step 1 targets, leg count and cutoff, and its `target_status` is not `targets_unavailable`; the same holds for a v4 basis.
  - `tests/meta/test_level_rule_version_readers.py::test_only_the_helper_and_the_population_compare_the_version`: an `ast` scan of `lib/`, `gcp/` and `platform/` for a comparison (`==`, `!=`, `in`, `not in`) with a `LEVEL_RULE_VERSION` name on either side, and for the name passed as a query parameter. The allowed sites, by file and enclosing function: `lib/strat_levels.py::is_current_pick_rule` (through `PICK_RULE_VERSIONS`), and `lib/movement_statement.py::_fetch_reach_rates` and `_reach_rate_sql` (the two population lines). Any other site fails with its file and line.
  - Review Focus, in `tests/lib/test_strat_levels.py`: `SessionLevels.from_basis(v3_basis).with_premarket(snap).rule_version == 'feat-strat-001.v3'` with its targets spaced as v3; `is_current_pick_rule(None)`, `('feat-strat-001.v1')` and `('feat-strat-001.v2')` are False.
- [ ] **Step 3: Run:** `python3 -m pytest tests/lib/test_strat_levels.py tests/lib/test_movement_statement.py tests/gcp/test_premarket_playbook_resolver.py tests/meta/test_level_rule_version_readers.py -q -k "v3 or rule_version or mix or only_the_helper"` (expect FAIL: `is_current_pick_rule` not defined).
- [ ] **Step 4: Implement.** The four readers call the helper: `lib/movement_statement.py:499`, `gcp/premarket_playbook_resolver.py:611`, `lib/strat_levels.py:1968` and `:2434`.
- [ ] **Step 5: Update the tests that pin the old label,** and list each for B11: `tests/lib/test_strat_levels.py:1477` and `tests/gcp/test_level_basis.py:460` assert the literal `'feat-strat-001.v3'`; `tests/fixtures/atr_levels_brief_base.json` holds it as a stored basis and stays as it is (a stored v3 basis is the case under test). Run `grep -rn "feat-strat-001.v3" tests` and decide each hit the same way: a stored basis stays v3, an assertion about the current version moves to v4.
- [ ] **Step 6: Run** `python3 -m pytest tests/lib tests/gcp tests/api tests/meta -q -k "level or movement or resolver or strat or brief"` (expect all passed), then the render step.
- [ ] **Step 7: Commit:** `feat(levels): mark the new premarket extremes as rule v4 and read v3 as before`

### Task 9: A replay that writes nothing

Spec: Problem 5; Design 5 (first three bullets and the last); decision 6. Closes B9.

**Files:**
- Modify: `gcp/premarket_brief.py` (`persist_to_cloud_sql` `:3598-3956`; `generate_premarket_brief` `:957`, `:1032`, `:1433-1488`; `main` `:4208-4372`)
- Create: `tests/gcp/brief_dry_run_helpers.py`
- Test: `tests/gcp/test_premarket_brief_no_discord.py` (class `TestNoPersist`)

**Interfaces:**
- Produces:
  - `PersistRows(NamedTuple)`: `rows: list[dict]`, `canonical: list[dict]`, `playbook_failed: frozenset[str]`, `stale_data: frozenset[str]`.
  - `build_persist_rows(brief: dict) -> PersistRows`: the row-building half of `persist_to_cloud_sql`, moved out unchanged. `rows` is every history row before `run_kind`, `triggered_by` and `notes` are added; `canonical` is the rows the canonical table would take, each with `run_kind` `'replay'` under `BRIEF_AS_OF` and `'live'` otherwise. It makes no query. `persist_to_cloud_sql` calls it.
  - `_resolve_no_persist(args) -> bool`: `--no-persist`, or `BRIEF_NO_PERSIST` equal to `true` after `strip().lower()`.
  - `generate_premarket_brief(cfg=None, data_dir: str = None, *, no_persist: bool = False, premarket_from_bars: bool = False) -> dict`. With `no_persist` it does not call `_delete_null_close_rows` or `persist_level_map`, and prints one `[brief:T] ... skipped (no-persist)` line for each.
  - In `tests/gcp/brief_dry_run_helpers.py`: `RecordingDb`, a stand-in for `gcp.database` and its engine that answers reads from frames the test gives, returns normally from every call, and records every statement text executed on a SQLAlchemy connection or a DBAPI cursor, every `commit`, and every call of `execute_sql`, `upsert_dataframe` and `bulk_insert_dataframe`; and `install(monkeypatch, db)`, which also replaces `lib.strat_levels.persist_level_map`, `pb._delete_null_close_rows` and `pb.persist_to_cloud_sql` with counting wrappers and sets `BRIEF_LLM_DISABLE=1`. Tasks 10 and 12 use both.

- [ ] **Step 1: Write the failing tests** in `TestNoPersist`. The fixture has three tickers: one with a null-close placeholder row before the session, one with a level map, one plain.
  - `test_the_flag_off_run_writes` (the control that shows the recorder sees writes): without the flag, the same fixture records one `_delete_null_close_rows` call, `persist_level_map` calls, a `commit`, and `persist_to_cloud_sql` called once.
  - `test_no_statement_but_a_select`: with `main(['--no-persist'])`, every recorded statement, stripped and upper-cased, starts with `SELECT` or `SET LOCAL STATEMENT_TIMEOUT`; `commit` count is 0; `execute_sql`, `upsert_dataframe`, `bulk_insert_dataframe`, `persist_level_map`, `_delete_null_close_rows` and `persist_to_cloud_sql` were each called zero times. The same with `BRIEF_NO_PERSIST=true` and no flag.
  - `test_it_prints_the_brief_the_rows_and_the_payloads`: `main()` returns without `SystemExit` (or exits 0); `capsys` holds the brief JSON, a section headed `--- rows (no-persist) ---` whose JSON equals `build_persist_rows(brief).canonical` with each row's `run_kind`, and every `--- payload i/n` block; `send_to_discord` was never called.
  - `test_persist_writes_exactly_the_built_rows`: with the flag off, the frames handed to `bulk_insert_dataframe` and `upsert_dataframe` hold exactly the tickers and values of `build_persist_rows(brief)`.
  - `test_refusals_exit_2_before_any_query`: `--no-persist` with `BRIEF_RUN_SLOT=late`, and with `--update`: `SystemExit(2)` and the recorder holds no statement.
  - Review Focus: `BRIEF_NO_PERSIST=TRUE` and `' true '` are on, `yes` is not; `BRIEF_UPDATE=true` with `--no-persist` exits 2; `BRIEF_POST_TO_DISCORD=true` with `--no-persist` calls `send_to_discord` zero times.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_brief_no_discord.py::TestNoPersist -q` (expect FAIL: unrecognised argument `--no-persist`).
- [ ] **Step 3: Move** the row building into `build_persist_rows` with no change of content, then run `python3 -m pytest tests/gcp/test_premarket_brief.py -q -k "Persist"` (expect all passed with no test edited: `git diff --stat -- tests/gcp/test_premarket_brief.py` shows only the additions of Tasks 1, 2 and 5).
- [ ] **Step 4: Implement** the flag, the two skips in `generate_premarket_brief`, the refusals placed before `load_config()` and any query, and the dry-run branch of `main`. Trace every other write the run can reach: run `test_no_statement_but_a_select` and read the recorder; any write it shows is suppressed the same way and named in the PR body.
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_premarket_brief_no_discord.py tests/gcp/test_premarket_brief.py tests/gcp/test_premarket_brief_late_slot.py -q` (expect all passed), then the render step.
- [ ] **Step 6: Commit:** `feat(brief): add a dry run that executes no write`

### Task 10: The dry run recomputes the premarket from the stored bars, at the brief's own cutoff

Spec: Problem 5 (last bullet); Design 5 (fourth bullet); decision 8. Closes B10.

**Files:**
- Modify: `gcp/premarket_brief.py` (`main`; `generate_premarket_brief` at the snapshot read, `:1354`)
- Test: `tests/gcp/test_premarket_brief_no_discord.py` (class `TestPremarketFromBars`)

**Interfaces:**
- Consumes: `generate_premarket_brief(..., premarket_from_bars=)` and `RecordingDb` (Task 9); `gcp.fetchers.fetch_market_data.premarket_snapshot` (`:380`) and `PREMARKET_COLUMNS`; `lib.strat_levels.read_live_level_basis` (`:2949`) and `premarket_snapshot_from_row`; `lib.eastern_time.eastern_bounds_utc`; `gcp.database.query_to_dataframe_strict`.
- Produces: `_premarket_from_bars(ticker: str, session_date: date, prior: dict, level_params, query_fn) -> tuple[dict | None, str]` returning `(snapshot, line)`: the eleven `PREMARKET_COLUMNS` values recomputed from the stored bars up to the cutoff, or `None`, and the line to print.

- [ ] **Step 1: Write the failing tests:**
  - `test_it_reads_bars_to_the_briefs_own_cutoff`: the live `premarket_analysis` row's `level_basis.premarket.fetched_at` is `2026-11-16T13:20:41+00:00`; `market_data_daily.pre_fetched_at` was rewritten to a later time and bars exist between the two. The bars statement binds `start` to 04:00 ET of the session and `end` to the brief's cutoff; no bar at or after the cutoff is in the frame given to `premarket_snapshot`; the recomputed high and low equal those computed by hand from the bars before the cutoff, written in the test.
  - `test_it_prints_stored_and_recomputed_side_by_side`: `capsys` holds one line a ticker with the ticker, `cutoff=`, `stored high=`, `stored low=`, `recomputed high=`, `recomputed low=`.
  - `test_the_recomputed_values_are_used_in_memory`: the brief's level basis for the ticker holds the recomputed `pre_high` and `pre_low`; the recorder holds no write (Task 9's assertions, repeated).
  - `test_no_cutoff`: no live row, and a row whose `level_basis` has no `premarket.fetched_at`, each print `premarket cutoff unavailable`, issue no bars read, and use the stored snapshot; `pre_fetched_at` of the daily row is never bound as the cutoff.
  - `test_no_bars`: an empty bars frame prints `premarket bars unavailable` and uses the stored snapshot.
  - `test_reads_are_strict_and_counted`: the bars read raising `ConnectionError` propagates out of `generate_premarket_brief`'s premarket step and is not printed as "unavailable"; for three tickers the recorder holds three bars statements and three live-basis statements (the Capacity figure).
  - `test_the_variable_needs_no_persist`: `BRIEF_PREMARKET_FROM_BARS=true` without `--no-persist` is `SystemExit(2)` with no statement recorded.
- [ ] **Step 2: Run:** `python3 -m pytest tests/gcp/test_premarket_brief_no_discord.py::TestPremarketFromBars -q` (expect FAIL: `_premarket_from_bars` not defined).
- [ ] **Step 3: Implement.** The bars statement is the nightly's own (`gcp/fetchers/fetch_market_data.py:575-582`: `SELECT ts, open, high, low, close, volume FROM market_data_intraday WHERE ticker = :ticker AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`), with `end` the earlier of the cutoff and 09:30 ET. `prior` is the last completed session's close, open, ATR(14) and ATR(5) as the brief already holds them for the ticker; the line printed also gives the ATR used beside the `atr` recorded in the stored row's `pre_filter_params`, so a difference is seen. The snapshot replaces the session row's eleven columns on a copy, and `premarket_snapshot_from_row` reads that copy.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_premarket_brief_no_discord.py tests/gcp/test_premarket_brief.py -q` (expect all passed), then the render step.
- [ ] **Step 5: Commit:** `feat(brief): recompute the premarket from stored bars in a dry run`

### Task 11: The 2026-11-16 session, from the stored bars

Spec: Problem 4 (the 11/16 prints); B8's second part; B6's IWM volumes. Closes B8 and B6. **Read-only production access: ask the owner once before running Step 1, together with Task 12 Step 2. Not assumed approved.**

**Files:**
- Create: `tests/fixtures/premarket_2026_11_16/` (`SPY_bars.csv`, `QQQ_bars.csv`, `IWM_bars.csv`, `brief_rows.json`, `daily_rows.json`, `iwm_daily_volumes.json`, the three tickers' daily frames and level parameter rows for Task 12, and `sources.json`)
- Test: `tests/lib/test_premarket_print_filter.py` (class `TestSession20261116`), `tests/lib/test_indicators.py`

**Interfaces:**
- Consumes: `calculate_premarket_context` (Task 6).
- Produces: `load_premarket_2026_11_16(ticker: str) -> tuple[pd.DataFrame, dict]` in the test module: the bars (`ts` aware UTC) and that ticker's entry of `brief_rows.json` and `daily_rows.json` (cutoff, stored extremes, prior close, ATR and thresholds).

- [ ] **Step 1: Export, on the owner's yes,** with `./scripts/db_query_cr.sh -q "<SQL>"` and no `--commit`. First check the bars are stored: `SELECT ticker, count(*) FROM market_data_intraday WHERE interval = '1min' AND ticker IN ('SPY','QQQ','IWM') AND ts >= '2026-11-16 09:00:00+00' AND ts < '2026-11-16 14:30:00+00' GROUP BY ticker`. Zero rows: the nightly has not written them; stop and say so, do not build the fixture from another source. Then:
  - the bars, a ticker: `SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= '2026-11-16 09:00:00+00' AND ts < '2026-11-16 14:30:00+00' ORDER BY ts` (04:00 to 09:30 ET; 2026-11-16 is on standard time, UTC minus 5);
  - the live brief rows: `SELECT ticker, analysis_ts, run_kind, rvol, ftfc_score, ftfc_labels, level_basis FROM premarket_analysis WHERE analysis_date = '2026-11-16' AND run_kind = 'live' AND ticker IN ('SPY','QQQ','IWM')`;
  - the daily rows of 2026-11-13 and 2026-11-16 for the three tickers, with close, open, the ATR columns and the eleven premarket columns;
  - `SELECT date, volume FROM market_data_daily WHERE ticker = 'IWM' AND date <= '2026-11-13' ORDER BY date DESC LIMIT 21`;
  - for Task 12's local run, what the brief's own reads return for the three tickers on that session: the daily frame `DataLoader.load_daily` reads and the rows `load_level_params` reads, with the statement text copied from the code at that time.
  `sources.json` names, per file, the db-query execution id, the SQL, the row count and the file's sha256.
- [ ] **Step 2: Write the tests:**
  - `TestSession20261116::test_sources_json_matches_the_files`: every file's sha256 and row count equal its entry, and the directory holds exactly the listed files.
  - `test_raw_highs_are_the_stored_ones`: for the bars before each ticker's recorded `level_basis.premarket.fetched_at`, with that row's prior close, ATR and thresholds, `confirmed['raw_high']` is 278.92 for IWM, 754.377 for SPY and 681.022 for QQQ.
  - `test_confirmed_extremes`: `pre_high` and `pre_low` of each ticker equal literals written in the test. Read each by hand from the fixture first (the second-highest surviving high, the highest surviving body, the bars the three rules dropped), write the working beside the literal as a comment, and only then run the code.
  - `test_the_0805_iwm_bar_is_thin`: the fixture's IWM 08:05 ET bar is counted in `thin['bars_excluded']` if its stored volume is under 100; if the stored bar differs from the vendor's read in the spec (volume 1, high 278.92), the test asserts what is stored and the difference is reported.
  - `TestRelativeVolume::test_iwm_to_2026_11_13` (Task 5 Step 6), if it was left out there.
- [ ] **Step 3: Run:** `python3 -m pytest tests/lib/test_premarket_print_filter.py::TestSession20261116 "tests/lib/test_indicators.py::TestRelativeVolume" -q` (expect all passed). Record the red for the PR body: on a checkout of the base commit the class fails with `KeyError: 'confirmed'`. A raw high that is not the stored value, a hand-read extreme the code does not return, or an IWM ratio that is not 0.7324 is a finding reported to the owner with the bars, never a changed expectation.
- [ ] **Step 4: Commit:** `test(levels): pin the confirmed extremes of 2026-11-16 on the stored bars`

### Task 12: Evidence, the thin bar count and the whole suite

Spec: Problem 3's table; Problem 4 (the 100 share starting value); Done when B11 and B7b. Closes B11 and B7b; completes B7c's named measurement.

**Files:**
- Create: `tests/gcp/run_brief_2026_11_16.py`

- [ ] **Step 1: The RVOL table on the PR head.** Run `grep -rn -i -E "rvol|vol_ratio" lib gcp platform/api scripts --include=*.py`, and set each of the spec's 17 rows beside its file and line on this head and its stage, with `STAGE_2` of Task 5 beside it. A row whose line moved gets its new line; a hit in no row is reported.
- [ ] **Step 2: The thin bar count, on the owner's yes (asked with Task 11).** Read only, through `gcp.fetchers.export_intraday_bars.read_bars` over `gs://<GCS_BUCKET>/intraday-bars/v1/1min/`: for each premarket session of SPY, QQQ and IWM in the stored history, compute the extremes with `PM_MIN_EXTREME_VOLUME` at 100 and at 0, and report per ticker how many sessions change `pre_high` and how many change `pre_low`, with the ten largest changes named by date. One ticker-month in memory at a time. The number goes to the owner with the PR; the value 100 is kept or changed on the owner's word, not here.
- [ ] **Step 3: The local dry run.** `python3 tests/gcp/run_brief_2026_11_16.py` sets `BRIEF_AS_OF=2026-11-16`, `BRIEF_TICKERS=SPY,QQQ,IWM` and `BRIEF_PREMARKET_FROM_BARS=true`, installs `RecordingDb` (Task 9) answering the brief's reads from `tests/fixtures/premarket_2026_11_16/`, and calls `gcp.premarket_brief.main(['--no-persist'])`: the production entry point, with only the database replaced. It prints, per ticker, the overview, the TF bias line, RVOL and the call and put triggers beside the stored row's values from `brief_rows.json`, and the recorder's write count (expect 0). Reads the fixture cannot answer (earnings, calendar, gamma) answer empty or unavailable, and the PR body says which. The model is called only where a Vertex credential is present; otherwise `BRIEF_LLM_DISABLE=1` is set, the output shows `deterministic_overview`, and the PR body says the model's overview is checked in Close-out step 3.
- [ ] **Step 4: The changed expectations.** Run `python3 -m pytest tests/lib/test_premarket_print_filter.py tests/gcp/test_premarket_filter_callers.py tests/lib/test_brief_planner_parity.py -q` (expect all passed) and write out every expectation Tasks 1, 2, 6, 7 and 8 changed: test, old value, new value, why.
- [ ] **Step 5: B7b's statement.** Rerun `git ls-tree $(git merge-base HEAD origin/main) lib/bar_prints.py`; put the merge base's sha and the output in the PR body with the sentence that Design 4 "Order" step 2 stays open for its own spec.
- [ ] **Step 6: Run:** `make test` in its normal order (expect no failure the base does not have).
- [ ] **Step 7: Run:** `git diff --stat origin/main -- gcp/schema.sql gcp/deploy.sh lib/level_calibration.py gcp/signal_monitor.py lib/strategies lib/signals.py lib/backtest.py lib/trading_analysis.py lib/agents platform/api scripts/calibrate_thresholds.py` (expect empty). This is a check the implementer runs by hand on the branch; it is not a test.
- [ ] **Step 8: Commit:** `test(brief): add the local dry run of the 2026-11-16 brief`

### Task 13: Close: product record, site note and the gate

Spec: Capability; Done when B12; product-delivery Phase 4 and Phase 5. Closes B12. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them: the source hash covers those paths.

- [ ] Push with `git push -u origin feature/feat-playbook-001-brief-says-what-the-data-says` and open a **draft** PR. Body: the spec's and this plan's paths; the done_when items B1 to B12 as `- [ ]` lines; `Red then green`; a Capacity section (Volume, Velocity, Wall-clock, Cost) with the Global Constraints figures; Task 12's five results with their execution ids; the "Choices" list of this plan; and the two notes under Close-out below.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-PLAYBOOK-001` record (`:205-224`): append this PR to the Status text (implementation under review, not deployed), and set Last reviewed to the date of the PR's head commit.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-PLAYBOOK-001` (`:631`): append the PR to its lineage, naming spec PR #1993. Commit both docs and the plan: `docs(product): record the brief corrections under FEAT-PLAYBOOK-001`.
- [ ] Site note, step 1: with a clean tree, `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] Site note, step 2: in `docs/product/03-SITE-TRACEABILITY.md`, the `| FEAT-PLAYBOOK-001 | DASHBOARD-01 |` row (`:1334`) and no other byte: the new hash, then this change's prose (the briefing strip's RVOL is `lib.indicators.relative_volume` from the first brief after the deploy; the brief's premarket high and low follow the confirmed, thin bar and closing-price report rules and its level basis is rule v4; tests named), then ` Earlier: ` and the earlier prose unchanged. Commit: `docs(site): note the brief corrections on DASHBOARD-01`.
- [ ] Site note, steps 3 and 4: run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0). If `origin/main` moved, update the branch, re-render and redo the four steps.
- [ ] Render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass).
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports no line that `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push; tick each done_when box with its evidence; only then mark the PR ready. Gate files are not touched, so no red-team pass is owed.

## Close-out (not tasks; the owner's steps)

From the spec's Close-out. None is done by the implementer, none is a done_when box, and each, read-only ones included, starts on the owner's own yes.

- **In the spec's order:** (1) deploy from `main` at or after the merge; (2) replay 2026-11-16 with no write, with the spec's command and its before and after checks; (3) check against market data; (4) the first scheduled brief after the deploy; (5) browser proof for the briefing strip's RVOL; (6) on a `docs/` branch, the DASHBOARD-01 note and this plan's `status: done`.
- **Deploy targets the spec asks this plan to name:** `./gcp/deploy.sh premarket` (the brief job, `:5370`) and `./gcp/deploy.sh market-data` (`fetch-market-data` and `fetch-premarket-refresh`, `:5397`). `backfill-ticker` is deployed by `deploy_backfill_ticker` (`:1294`), which the `discord` target runs (`:5429`).
- **A deploy order the spec does not state, for the owner to decide before step 1.** The first brief built by the new image writes `rule_version` v4. An image that still compares with the v3 constant reads a v4 basis as "another version": the playbook resolver then returns `targets_unavailable` (`gcp/premarket_playbook_resolver.py:625-628`) and the movement statement drops the cleared mark (`lib/movement_statement.py:499`). Every image that reads `level_basis` (the playbook resolver, the API, the signal monitor, the insight pipeline) needs `is_current_pick_rule` before the first v4 brief, so the readers deploy before or with the brief job. This was read from the code, not tested against a deployed image.
- **`--recompute-premarket` is not run.** `pre_filter_params` now carries two more blocks, so a later recompute would report every session as changed. That is expected and belongs to whoever runs it.
