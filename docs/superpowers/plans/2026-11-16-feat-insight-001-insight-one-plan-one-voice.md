---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md
branch: feature/feat-insight-001-insight-one-plan-one-voice
pr: null
status: ready
---

# AI Insights: one plan, the brief's, and one voice about it: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are named by the spec's own labels, D1 to D12 with D3b, D5b, D7b and D11b: sixteen items.

**Goal:** For a ticker the premarket brief covers, the insight report reads its levels, indicators, trigger, stop and targets from the session's stored `premarket_analysis` row and recalculates none of them; the risk critics and the portfolio manager are shown the plan that is published; and no published flag, thesis, case or invalidation names a price or a conviction the report does not hold. Max pain becomes true max pain beside a separately named largest open interest strike, and key levels get a stated order.

**Architecture:** `lib/agents/summarizers.py` gains one strict reader of the brief row (`summarize_brief_row`) and `build_context_bundle` fills the `market`, `strat` and `session_levels` sections from it for a brief ticker. `lib/strat_levels.py` gains one reader of the stored side records (`read_stored_sides`); `lib/agents/trade_planner.py` publishes those records as the plan and computes the five numeric risk rules. `lib/agents/orchestrator.py` reorders the run (plans and rule flags before the risk tier, conviction before the portfolio manager) and checks every model sentence against the plan with one pure function, `cited_prices_outside`. The model requests stay at 14.

**Tech Stack:** Python, pandas, pydantic, pytest (`monkeypatch`, `caplog`), the stub `LLMClient` of `tests/agents/test_agent_orchestrator.py`, Starlette `TestClient` for the API test.

**Spec:** docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md (approved, merged in PR #1992, read on `origin/main` aa163a8e3). Executors read the spec and this plan together.

## Scope of this plan

- One plan, one branch, one PR, 12 tasks, the spec's own count ("12 tasks, one branch, one PR").
- **No done_when item is out of this plan.** All sixteen are closed by a task (see the map).
- The spec's Close-out (deploy, the `INSIGHT_AS_OF` replay, the market check, the browser runs, the post-merge docs) is the owner's and is not a task: "None of these runs from the implementation PR, and none is a `done_when` box."

## Open questions for the owner (one line each, before the task named)

The spec contradicts itself or the code in these places. The plan states the reading it builds on; none is settled silently.

1. **Bare integer `999` (before Task 6 Step 1).** D6 says "'$999' and '999' beside a plan near 277 are outside". Design 3 says a citation is "a number written with a `$`, or with a decimal part, or an integer within 20 percent of the plan's entry". A bare `999` is none of those beside an entry of 275.86, so under Design 3 it is not read at all and cannot be "outside". This plan builds Design 3's rule (the Risks section argues from it) and tests `$999` as outside. The bare `999` clause of D6 cannot be ticked until the owner says which text stands; a spec correction is a docs PR.
2. **N1's wording (before Task 5 Step 1).** D5 quotes 'Stop 0.32x ATR from entry'. Design 3 says "the severities and wording the prompts hold today", and the prompt reads "Stop only {x:.2f}x ATR from entry midpoint; empirically -31.1pp win-rate" (`lib/agents/prompts.py:226-227`). This plan keeps the prompt's sentence and asserts on `0.32x ATR from entry`, which both hold.
3. **`lib/strat_levels.py` (no action needed unless struck).** Non-goals say "No change to the brief, to `lib/strat_levels.py`"; Design 2 and D3b add `lib.strat_levels.read_stored_sides`. This plan adds that one reader and removes or edits no existing line of the file.

## Dependency on the brief spec

`docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md` is approved and not implemented. From what the two specs say:

- **Nothing in this plan's code or tests waits for it.** The insight reads columns `premarket_analysis` already has, and every test here runs on the stored 2026-11-16 row and report, exported once (Task 1).
- **The values follow the row.** The brief spec changes how `pre_high`, `pre_low` and `rvol` are computed (its B6, B7, B7a, B7c). The insight "follows whatever the row holds" (this spec, Non-goals), so it needs no change when the brief lands, and until then it publishes the brief's values as they are, the 278.92 premarket high of IWM included.
- **The rule version.** The brief spec moves `LEVEL_RULE_VERSION` to `feat-strat-001.v4` (B8b). `read_stored_sides` reads the side records whatever version wrote them. Only one clause leans on the other spec: D3b's comparison "`SessionLevels.from_basis` of the same basis gives stop 277.41 and target 269.875" is on a v3 basis, and it holds after the bump only because B8b promises "`from_basis` of a stored v3 basis returns the picks it returns on origin/main".
- **The replay in Close-out depends on the brief row staying live.** The brief spec's Close-out says the insight replay "needs the 11/16 brief row left live". On `main` today a `BRIEF_AS_OF=2026-11-16` run restamps that row `replay` (brief spec, Problem 5), after which the insight would publish `brief_row_missing` for 11/16. So no brief replay of 11/16 may run before the brief spec's `--no-persist` (B9) is deployed. The brief's dry run writes no row, so the insight replay shows the plan of the row stored at 13:31:23Z, not a corrected premarket high.
- **Shared files, whichever PR merges second rebases.** `tests/lib/test_brief_planner_parity.py` (the brief spec's B11 lists it; Task 4 here changes it), `lib/strat_levels.py` (B8b edits `:1968` and `:2434`; this plan appends), and, if the brief merges first, `tests/meta/test_one_rvol_definition.py` (B6b), which scans for keys named `rvol`: Task 2 adds one in `summarize_brief_row`, a value read from the brief's column, and that test must be run and its list followed.

## Global Constraints

- Base: `origin/main` at or after aa163a8e3. The spec's line references were read on 4155a10f and 060c89a0 and hold on aa163a8e3 (checked for this plan), with one slip noted under "Where the spec and the code differ". Branch `feature/feat-insight-001-insight-one-plan-one-voice`. This plan is committed alone on `docs/plan-feat-insight-001-insight-one-plan-one-voice` and merged before the code branch opens.
- No schema change: `gcp/schema.sql` is not in the diff. `brief_ref`, `key_level_order` and `key_level_order_basis` are fields of the report JSON.
- No new model call: exactly 14 requests a report (6 analysts, 2 researchers, judge, trader, 3 risk, portfolio manager). No second call on a withheld flag or a replaced narrative.
- No Discord layout change: no embed field added, removed, renamed or moved. The existing assertions of `tests/gcp/test_insight_discord_push.py` on the embed's fields, their names and their order pass unmodified.
- Not in the diff: `gcp/premarket_brief.py`, `gcp/brief_explanations.py`, `gcp/schema.sql`, `gcp/deploy.sh`, `lib/strat.py`, `lib/gamma.py`, `lib/level_calibration.py`, `lib/indicators.py`, `platform/api/routers/`, and nothing in solyra. `lib/strat_levels.py` shows added lines only.
- Unchanged rules: `_calibrate_conviction`'s decision tree, the thresholds of N1, N2, N3, C1 and C2, the FTFC weights, `_SIZE_BY_CONVICTION` and the conservative gates, every gamma level.
- Nothing PR #1831 owns: no `plan_status` field, no plan hash, no `report_consistency.py`, no reviewer quorum, and the two `or 0.0` reads of the FTFC score (`lib/agents/orchestrator.py:554`, `lib/agents/trade_planner.py:641`) stay as they are with their `AUDIT-2026-05-13` marker.
- No silent fallback (CLAUDE.md 3.7): a null column is null in the section, a missing stop is null and never 0, a missing row is `brief_row_missing` and never a rebuilt value, and no R-multiple target stands in for a missing one.
- Exact strings, copied from the spec:
  - reasons `brief_row_missing`, `brief_plan_missing`, `stop_missing`, `narrative_conflict`
  - withheld flag: `A {persona} reviewer's note was withheld: it cited a price that is not in the plan.`
  - no-stop invalidation: `The brief's plan has no stop in its window, so no invalidation price is given.`
  - invalidation: `Stop 277.41 (PQL): the plan is invalid beyond it.`
  - deterministic sentence: `Short, low conviction. Entry 275.86 (PMK_L), stop 277.41 (PQL), target 269.88 (PML).`
  - key level names `Max Pain (exp MM/DD)` and `Largest OI Strike (all exp)`; order bases `distance_from_reference` and `price_desc_no_reference`
- Tests are hermetic. CI's Run Tests job checks out one commit with no `origin/main`, so no test runs `git show`, `git diff` or any other git command; a value "on origin/main" is pinned by a literal or a fixture file. No test opens a socket, reads a database or calls a model: models are the stub `LLMClient` classes of `tests/agents/test_agent_orchestrator.py`. "Fails on origin/main" is shown by the red run of each new test on the branch before its code step, recorded in the PR body.
- Production access from this branch is read-only and is two dispatches of `scripts/db_query_cr.sh` without `--commit`: Task 1 (the fixture export) and Task 12 (the EXPLAIN). **Ask the owner once before each; neither is assumed approved.** No deploy, no replay, no job execution, no write.
- Capacity (CLAUDE.md Rule 0; spec Design 7), for the PR body: one brief row per ticker in one strict read, in place of the strat and session-level reads, plus one strict read of the brief's ticker list (Task 3), each under 2 s; the options read returns one snapshot (5,024 rows IWM, 11,052 QQQ, 12,738 SPY on 11/13) against 386,848, 828,900 and 955,608 today; 14 model calls unchanged; no new job or schedule. The options read's wall-clock is measured in Task 12.
- The render step. A task that changes a file under `gcp/`, `lib/` or `scripts/` ends with it, because the generated inventory cites line numbers:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed), and stage whichever of the three docs changed with the code.
- Existing tests that change. Tasks 3 to 10 change behaviour that tests outside the spec's list assert today (385 tests pass on aa163a8e3 across `tests/lib/test_trade_planner.py`, `tests/lib/test_trade_planner_distance_cap.py`, `tests/agents`, `tests/lib/test_brief_planner_parity.py`, the two `tests/api/test_insight_report_*.py` files and `tests/gcp/test_insight_discord_push.py`). Each task runs that set; every assertion changed or removed is listed in the PR body by file, test name and the Design section that changes it. No test is deleted without being named there.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. The PR opens as a draft and stays one until every done_when line in its body is ticked with evidence.
- Choices this plan makes where the spec leaves one open (reported to the owner with the plan):
  - **Which tickers are brief tickers.** The spec names the source (`watchlists` rows with `in_brief = TRUE`) and no reader. `gcp.fetchers._watchlist.load_watchlist` returns `[]` on a failed query, which would send every ticker down the builder path. So Task 3 adds a strict reader that raises, and a failed list read fails the run.
  - **An outage on the brief row read** is caught by `build_context_bundle`'s existing handler: the three sections are unavailable with reason `exception: <Type>: <text>`, never `brief_row_missing`.
  - **Keys the row does not hold.** A brief ticker's `market` section carries only what the row holds; `regime`, `bb_pct`, `price_vs_ema20_pct`, `macd` and `macd_histogram`, which `summarize_market_context` computes today and the spec's Problem 2 table does not list, are absent, not recalculated.
  - **Tickers outside the brief** keep today's readers and builder (decision 2), and their plan is read from the side records of the basis that builder wrote in the same run, since Design 2 removes the buffers, the persona stop and the R multiples from `_plan` for every ticker.
  - **An unavailable plan** is three `PersonaPlan` entries with null entry and stop, no targets, size 0.0 and a rationale naming the reason, with `persona_plans` in `failed_sections`. No status field is added (PR #1831 owns `plan_status`).
  - **The portfolio manager's numbers are never the headline.** Design 4 says its entry, stop and targets "are not published", so the fallback at `lib/agents/orchestrator.py:637-643` is removed.
  - **Flat and unavailable invalidation.** Flat: the empty string. A plan that is unavailable: `No plan is published (<reason>), so no invalidation price is given.`
  - **`StratSnapshot.trigger_high` and `.trigger_low`** stay in `lib/agents/schema.py` as optional fields so stored reports still load; nothing writes them.
  - **One snapshot, twice.** The options SQL selects one snapshot and the function also keeps only the latest `snapshot_ts` of the frame it was given, so D9's hermetic two-snapshot frame tests the function and not only the SQL text.
  - **Fixture files beyond the level_basis.** Task 1 also exports the three stored reports whole (D11 prints beside them) and the three brief rows (D2 compares "column for column").

## done_when map

| done_when | What | Task |
|---|---|---|
| D1 | `summarize_brief_row` | 2 |
| D2 | nothing the brief holds is recalculated | 3, 4 |
| D3 | the insight's plan is the brief's plan | 1, 4 |
| D3b | the stored pick is read, never re-picked | 4 |
| D4 | critics review the published plan | 6 |
| D5 | numeric flags are computed, published, and cap conviction | 5, 6 |
| D5b | a plan without a stop publishes as one | 4, 5, 8 |
| D6 | a flag cannot cite a price outside the plan | 6 |
| D7 | one conviction | 7 |
| D7b | a narrative naming an off-plan price is replaced | 7 |
| D8 | invalidation is the plan's stop | 8 |
| D9 | max pain is max pain | 9 |
| D10 | key level order, Discord layout unchanged | 10 |
| D11 | evidence in the PR body | 1, 12 |
| D11b | the changed API response is tested | 11 |
| D12 | records | 12 |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **A brief row that exists but is thin.** Null `ftfc_score`, null `atr14`, a null `level_basis`, or a `level_basis` whose `status` is `stale_daily`: each null stays null in its section, the plan is unavailable (`brief_plan_missing`, or the basis's own status), and nothing is rebuilt or read as 0. Tasks 3 and 4.
- **An outage that looks like a missing row.** The brief row read or the brief list read raising `ConnectionError` inside the bundle: never reported as `brief_row_missing`, and the list read's failure fails the run instead of sending the ticker down the builder path. Task 3.
- **How a model writes a number.** `$1,234.50`, `277.41.` at the end of a sentence, `275.86-277.41`, `0.75 x ATR` with a space, `1.5R`, `-24.9pp`, `11/16`, `2026`, `250 sessions` beside an IWM entry of 275.86 (inside the 20 percent band), and `200 SMA`. A reader expects a real price read once, a measurement, a date or a count not withheld, and no exception. Task 6.
- **A stored side record that is odd but valid.** A stop on the wrong side of the entry, a target equal to the entry, four targets, a target whose `price` is null, and a basis with `atr` null: the plan publishes what is stored, the metrics that cannot be measured are null, and nothing raises. Task 4.
- **A report stored before this change.** No `key_level_order`, a key named `Max Pain`, `strat_status.trigger_high` set: Discord and the API serve it as before. And a `key_level_order` that names a key the dict lacks, or omits one it has: every key the dict has is rendered once. Task 10.

## File map

| File | Change | Task |
|---|---|---|
| `tests/fixtures/insight_2026_11_16/` | new: nine JSON files and `sources.json` | 1 |
| `tests/agents/insight_2026_11_16.py` | new: fixture loaders shared by five test files | 1 |
| `lib/agents/summarizers.py` | `summarize_brief_row`, `brief_tickers`, the bundle wiring (`:2027-2106`); `summarize_strat_status` (`:480-492`); `summarize_options_flow` (`:655-738`) | 2, 3, 8, 9 |
| `lib/agents/schema.py` | `InsightReport`: `brief_ref`, `key_level_order`, `key_level_order_basis` (after `:347`) | 3, 10 |
| `lib/strat_levels.py` | new, appended beside `read_live_level_basis` (`:2949`): `StoredSides`, `StoredPlanMissing`, `read_stored_sides` | 4 |
| `lib/agents/trade_planner.py` | `PlanContext` (`:56-107`), `compute_persona_plans` and `_plan` (`:189-343`), `compute_risk_metrics` (`:346-401`), `context_from_bundle` (`:561-645`); new `size_persona_plans`, `compute_rule_flags` | 4, 5 |
| `lib/agents/prompts.py` | `TRADER_PROMPT` (`:168`), `RISK_PERSONA_PROMPTS` (`:175-242`), `PORTFOLIO_MANAGER_PROMPT` (`:245-279`) | 5, 6, 7, 8 |
| `lib/agents/orchestrator.py` | `_risk_payload` (`:226-238`), `_portfolio_payload` (`:241-265`), `run_insight_pipeline` (`:405-713`), `_PRICE_PATTERN` and `_validate_thesis_consistency` (`:735-822`), `_derive_key_levels` (`:952-1110`), `_build_strat_snapshot` (`:1120-1143`) | 3, 6, 7, 8, 9, 10 |
| `gcp/insight_discord_push.py` | `_fmt_levels_field` (`:140-152`) and its one call (`:529`) | 10 |
| `tests/agents/test_agent_summarizers.py` | `TestBriefRow`, `TestMaxPain` | 2, 9 |
| `tests/agents/test_brief_is_the_source.py` | new | 3, 4 |
| `tests/agents/test_trade_planner.py` | new: `TestBriefPlan`, `TestStoredSides`, `TestMissingStop`, `TestRuleFlags` | 4, 5 |
| `tests/agents/test_agent_orchestrator.py` | `TestOneVoice`, `test_key_level_order`, a recording stub | 6, 7, 8, 10 |
| `tests/gcp/test_insight_discord_push.py` | `test_levels_render_in_report_order`, added only | 10 |
| `tests/api/test_insight_report_brief_plan.py` | new | 11 |
| `tests/agents/test_insight_2026_11_16_evidence.py` | new: the side by side print | 12 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json`, `docs/product/infrastructure/05-*` | close, and the render step | 12 |

`gcp/insight_pipeline_job.py` and `platform/api/routers/insights.py` are read by Task 11's test and are not changed: the job stores the report JSON whole (`_upsert_report`, `:373`) and the router returns it as a dict (`ReportEnvelope.report`, `:149`).

---

### Task 1: The 2026-11-16 fixture

Spec: Problem 1 (the stored report of 2026-11-16 13:46Z); D3's fixture clause; Implementation plan item 1. Advances D3 and D11. **Read-only production access: ask the owner once before Step 1 and do not run it without a yes.** Tasks 2, 3, 5, 9 and 10 do not read these files and can proceed while the answer is pending; Tasks 4, 6, 7, 8, 11 and 12 cannot.

**Files:**
- Create: `tests/fixtures/insight_2026_11_16/{IWM,QQQ,SPY}_stored_report.json`, `{IWM,QQQ,SPY}_level_basis.json`, `{IWM,QQQ,SPY}_brief_row.json`, `sources.json`
- Create: `tests/agents/insight_2026_11_16.py`
- Test: `tests/agents/test_trade_planner.py` (new file; this task adds one test)

**Interfaces:**
- Produces, in `tests/agents/insight_2026_11_16.py`:
  - `TICKERS = ("IWM", "QQQ", "SPY")`, `SESSION = date(2026, 11, 16)`
  - `level_basis(ticker: str) -> dict` (a fresh deep copy each call, so a test may edit it)
  - `stored_report(ticker: str) -> dict`
  - `brief_row(ticker: str, **overrides) -> pd.DataFrame`: one row with the columns of `BRIEF_ROW_SQL` (Task 2), from `<T>_brief_row.json`, its `level_basis` cell taken from `level_basis(ticker)` unless overridden
  - `EXPECTED_SHORT = {"IWM": (275.86, "PMK_L", 277.41, "PQL", [269.875]), "QQQ": (668.30, None, 679.89, "PDC", [662.02, 637.01]), "SPY": (747.95, None, 750.36, "PML", [741.025, 729.10])}`: entry, trigger name where the spec gives it, stop, stop name, targets, copied from D3

- [ ] **Step 1: Export, one dispatch, no `--commit`:**
  `./scripts/db_query_cr.sh -q "SELECT ticker, as_of, run_kind, report FROM insight_reports WHERE ticker IN ('IWM','QQQ','SPY') AND run_kind = 'live' AND as_of >= '2026-11-16 13:40:00+00' AND as_of < '2026-11-16 14:00:00+00' ORDER BY ticker; SELECT analysis_date, analysis_ts, run_kind, ticker, price, rsi, sma200, ema9, ema20, atr14, bb_upper, bb_lower, rvol, volatility_20d, vol_regime, macd_cross, above_sma200, strat_candle, strat_combo, strat_setup, ftfc_score, ftfc_direction, ftfc_labels, tf_continuity, tf_continuity_frames, prev_day_high, prev_day_low, level_basis FROM premarket_analysis WHERE analysis_date = '2026-11-16' AND ticker IN ('IWM','QQQ','SPY') AND run_kind = 'live' ORDER BY ticker"`
  Expect three rows from each statement. Read `results.json` from the execution's bucket prefix. Write each stored report and each brief row with `json.dumps(obj, sort_keys=True, indent=1)`; `<T>_level_basis.json` is the stored report's `level_basis`, written the same way.
- [ ] **Step 2: Write `sources.json`:** the db-query execution id, both SQL texts, and per file its row source, byte count and sha256. Add `level_basis_equal`: per ticker, whether the report's `level_basis` equals the brief row's, and the differing top-level keys when it does not (the spec's "not compared"). A difference inside a `long` or `short` record is reported to the owner before Task 4 starts.
- [ ] **Step 3: Write the loader module and one test** in `tests/agents/test_trade_planner.py`:
  - `test_fixture_matches_sources_json`: the directory holds exactly the ten files; every file's sha256 and byte count equal its `sources.json` entry; for each ticker `level_basis(t)["short"]["trigger"]["price"]`, `["short"]["stop"]["price"]` and `[x["price"] for x in ["short"]["targets"]]` equal `EXPECTED_SHORT[t]`, and IWM's `atr` is 4.87495. A mismatch with the spec's numbers is a finding for the owner, never a changed expectation.
- [ ] **Step 4: Run:** `python3 -m pytest tests/agents/test_trade_planner.py -q` (expect 1 passed).
- [ ] **Step 5: Commit:** `test(insight): add the stored 2026-11-16 reports and brief rows as fixtures`

### Task 2: `summarize_brief_row`

Spec: Design 1, first two bullets. Closes D1.

**Files:**
- Modify: `lib/agents/summarizers.py` (new function after `_live_level_basis`, `:526-530`)
- Test: `tests/agents/test_agent_summarizers.py`

**Interfaces:**
- Consumes: `_query_strict` (`:59`), `_session_date_for` (`:502`), `lib.strat_levels.parse_level_basis` (`:2936`).
- Produces:
  - `BRIEF_ROW_MISSING = "brief_row_missing"`
  - `BRIEF_ROW_SQL`: one statement selecting the 28 columns of Task 1's second statement from `premarket_analysis` with `WHERE ticker = :ticker AND analysis_date = :d AND run_kind = 'live' LIMIT 1`
  - `summarize_brief_row(ticker: str, as_of: Optional[date_type] = None) -> dict`. With a row: `{"available": True, "price", "rsi", "sma200", "ema9", "ema20", "atr14", "bb_upper", "bb_lower", "rvol", "volatility_20d", "vol_regime", "macd_cross", "above_sma200", "strat_candle", "strat_combo", "strat_setup", "ftfc_score", "ftfc_direction", "ftfc_labels", "tf_continuity", "tf_continuity_frames", "prev_day_high", "prev_day_low", "level_basis", "brief_ref": {"analysis_date": "YYYY-MM-DD", "analysis_ts": ISO 8601 UTC, "run_kind": "live"}}`, each value as stored, a null as `None`, JSON cells parsed to dicts. With no row: exactly `{"available": False, "reason": "brief_row_missing"}`.

- [ ] **Step 1: Write the failing tests** in a class `TestBriefRow`, with `_query` replaced by a stand-in that raises and `_query_strict` by a recorder that answers from `insight_2026_11_16.brief_row("IWM")` (while Task 1 is pending, from a one-row frame written in the test with the same columns):
  - `test_one_strict_read_of_the_live_row`: `summarize_brief_row("iwm", date(2026, 11, 16))` made one call; its SQL names `premarket_analysis` and `run_kind = 'live'`; its parameters are `{"ticker": "IWM", "d": "2026-11-16"}`.
  - `test_returns_every_column_and_brief_ref`: each of the 24 value keys equals the frame's cell; `brief_ref` equals the row's `analysis_date`, `analysis_ts` and `run_kind`; `ftfc_labels == {"1d": "2D", "1w": "1", "1mo": "2U"}` for IWM.
  - `test_null_column_stays_null`: a frame with `ftfc_score` and `atr14` NaN returns `None` for both, not 0.0.
  - `test_no_row_is_brief_row_missing`: an empty frame returns exactly `{"available": False, "reason": "brief_row_missing"}`.
  - `test_read_failure_raises`: the recorder raising `ConnectionError("connection refused")` propagates unchanged.
  - `test_live_run_uses_the_eastern_session_date`: with `as_of=None` and `_session_date_for` replaced to return `date(2026, 11, 16)`, the `d` parameter is `"2026-11-16"`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_agent_summarizers.py -k TestBriefRow -q` (expect FAIL: `summarize_brief_row` not defined).
- [ ] **Step 3: Implement.** No `try` around the read. No `level_basis IS NOT NULL` filter: a row with a null basis is a row.
- [ ] **Step 4: Run** the same command (expect 6 passed), then the render step.
- [ ] **Step 5: Commit:** `feat(insight): read the session's brief row in one strict read`

### Task 3: The bundle reads the row, and the report says which

Spec: Design 1, bullets three to seven; decisions 2, 3 and 4. Advances D2 (the bundle and `brief_ref` clauses).

**Files:**
- Modify: `lib/agents/summarizers.py` (`build_context_bundle`, `:2027-2106`), `lib/agents/schema.py` (`InsightReport`, after `:347`), `lib/agents/orchestrator.py` (`run_insight_pipeline` signature `:273-281`, the bundle call `:311`, the report `:645`)
- Create: `tests/agents/test_brief_is_the_source.py`

**Interfaces:**
- Consumes: `summarize_brief_row`, `BRIEF_ROW_MISSING` (Task 2).
- Produces:
  - `brief_tickers() -> frozenset[str]`: one strict read, `SELECT ticker FROM watchlists WHERE user_id = :u AND removed_at IS NULL AND in_brief = TRUE` with `u = "default"`, upper-cased. A failed read raises.
  - `build_context_bundle(ticker, as_of=None, inclusive_today=False, *, universe=None, brief_tickers: Optional[frozenset[str]] = None) -> dict`. `brief_tickers=None` resolves the list by `brief_tickers()` before the section loop, outside its `try`. The bundle gains `"brief_ref"` (the row's, or `None`).
  - For a brief ticker with a row, the three sections, each with `"source": "brief_row"`:
    - `market`: `available`, `date` (the row's `analysis_date`), `close` (`price`), `rsi_14` (`rsi`), `sma_200` (`sma200`), `ema_9`, `ema_20`, `atr_14` (`atr14`), `bb_upper`, `bb_lower`, `rvol`, `volatility_20d`, `vol_tag` (`vol_regime`), `macd_cross`, `above_sma_200` (`above_sma200`), `premarket` (`level_basis["premarket"]`, or `None`)
    - `strat`: `available`, `date`, `last_candle` (`strat_candle`), `in_force_combo` (`strat_combo`), `strat_setup`, `ftfc_score`, `ftfc_direction`, `ftfc_labels`, `tf_continuity`, `tf_continuity_frames`, `prev_day_high`, `prev_day_low`
    - `session_levels`: `available` (the basis is a dict whose `status` is `ok`), `session_date`, `premarket_status` (the basis's), `level_basis` (the row's dict, the same object, not a `to_basis()` round trip); with a null basis, `reason: "brief_plan_missing"`; with a `status` that is not `ok`, that status as the reason
  - For a brief ticker with no row: the three sections are `{"available": False, "reason": "brief_row_missing"}`, each in `failed_sections` and `failed_section_reasons`.
  - For any other ticker: the three lambdas of `:2055-2057` as today (`session_levels["source"]` stays `"builder"` or `"level_basis"`), and `brief_ref` is `None`.
  - `InsightReport.brief_ref: Optional[dict] = None`.
  - `run_insight_pipeline(..., brief_tickers: Optional[frozenset[str]] = None)`, forwarded to the bundle; the report is built with `brief_ref=bundle.get("brief_ref")`.

- [ ] **Step 1: Write the failing tests.** A fixture `raising_builders` replaces `lib.strat.compute_strat_status`, `lib.strat_levels.build_session_levels`, `SessionLevels.with_premarket`, `SessionLevels.from_basis`, `lib.strat_levels._assemble` and `lib.level_calibration.calibrate_ticker` each by a stand-in that raises `AssertionError("recalculated")`. `_query_strict` answers `premarket_analysis` from `insight_2026_11_16.brief_row`; every other read returns an empty frame.
  - `test_sections_equal_the_row_column_for_column`: `build_context_bundle("IWM", date(2026, 11, 16), brief_tickers=frozenset({"IWM"}))` under `raising_builders`: every key listed above equals the row's cell; `session_levels["level_basis"] == insight_2026_11_16.level_basis("IWM")`; `bundle["brief_ref"]["analysis_date"] == "2026-11-16"`; none of `market`, `strat`, `session_levels` is in `failed_sections`; `"trigger_high" not in bundle["strat"]`.
  - `test_missing_row_makes_the_three_sections_unavailable`: an empty frame: the three sections are exactly `{"available": False, "reason": "brief_row_missing"}`, `failed_section_reasons` holds `brief_row_missing` for each, `bundle["brief_ref"] is None`, and no stand-in raised.
  - `test_other_ticker_keeps_the_builder_path`: `brief_tickers=frozenset({"IWM"})` with ticker `"NVDA"` and the readers of `tests/agents/test_agent_orchestrator.py`'s `canned_bundle`: `summarize_strat_status` was called, `bundle["brief_ref"] is None`, and `premarket_analysis` was not read through `BRIEF_ROW_SQL`.
  - `test_brief_ticker_list_is_one_strict_read`: `brief_tickers()` issues one statement naming `in_brief = TRUE` and returns the upper-cased set; the read raising `ConnectionError` propagates out of `brief_tickers()` and out of `build_context_bundle("IWM")`.
  - Review Focus: `test_row_read_outage_is_not_brief_row_missing`: the row read raising `ConnectionError`: the three sections are unavailable, each reason starts `exception: ConnectionError`, none is `brief_row_missing`. `test_thin_row`: `level_basis` null gives `session_levels` reason `brief_plan_missing` with `market` and `strat` still available; `level_basis.status == "stale_daily"` gives that reason; `ftfc_score` null is `None` in `strat`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_brief_is_the_source.py -q` (expect FAIL: unexpected keyword `brief_tickers`).
- [ ] **Step 3: Implement.** The row is read once per bundle and the three sections are built from that one dict. `summarize_strat_status`, `summarize_session_levels` and `summarize_market_context` are not called for a brief ticker.
- [ ] **Step 4: Run** the same command (expect all passed) and `python3 -m pytest tests/agents tests/api/test_insight_report_conservative_short.py tests/api/test_insight_report_trigger_distance_cap.py -q` (the existing fixtures do not cover the new read: `canned_bundle` in `tests/agents/test_agent_orchestrator.py:353` patches `summarizers._query` only, `_query_strict` (`lib/agents/summarizers.py:59`) calls `gcp.database.query_to_dataframe_strict` on its own, and the autouse watchlist fixture patches `load_watchlist`, which the strict reader bypasses; so this step first adds to `canned_bundle`, and to any fixture the two API suites build their bundle with, a `monkeypatch.setattr(summarizers, "brief_tickers", lambda: frozenset())`, which keeps their tickers on the builder path with no database call, and adds `test_no_fixture_reaches_the_database`: with `gcp.database.query_to_dataframe_strict` replaced by a function that raises `AssertionError`, the existing green-path test still passes; record any changed assertion), then the render step.
- [ ] **Step 5: Commit:** `feat(insight): fill market, strat and session levels from the brief row`

### Task 4: The plan is the stored plan

Spec: Design 2; decision 5; decision 11. Closes D2, D3 and D3b; advances D5b (`TestMissingStop`, its `compute_risk_metrics` clauses).

**Files:**
- Modify: `lib/strat_levels.py` (append after `read_live_level_basis`, `:2949-2965`), `lib/agents/trade_planner.py`, `lib/agents/orchestrator.py` (the plan block `:588-643`, only as far as the new signatures need; the reorder is Task 6)
- Test: `tests/agents/test_trade_planner.py`, `tests/agents/test_brief_is_the_source.py`

**Interfaces:**
- Consumes: the `session_levels` section (Task 3); a side record as `SideLevels.to_dict` writes it (`lib/strat_levels.py:1710-1720`): `trigger`, `stop` and each of `targets` are dicts with `name` and `price` (`_rung`, `:2695`), beside `regime`, `reason`, `window`, `target_status`, `plan`.
- Produces:
  - `lib.strat_levels.StoredPlanMissing(LookupError)`
  - `lib.strat_levels.StoredSides`: a frozen dataclass with `long: dict`, `short: dict`, `reference: Optional[float]`, `atr: Optional[float]`, `rule_version: Optional[str]`, and `side(direction: str) -> dict`
  - `lib.strat_levels.read_stored_sides(basis: dict) -> StoredSides`: the `long` and `short` values of the basis, the same objects, with `basis["reference"]`, `basis["atr"]` and `basis["rule_version"]`. Raises `StoredPlanMissing` when the basis is not a dict or either record is missing or is not a dict. Calls nothing else in the module.
  - `PlanContext`: `levels`, `prior_swing_low`, `prior_swing_high` and `analog_median_day_5_pct` are removed; added `stored: Optional[StoredSides] = None` and `unavailable_reason: Optional[str] = None`; `conviction: Optional[Conviction]`. `reference_price()` returns `stored.reference` when set, else `close`.
  - `context_from_bundle(bundle: dict, direction: Direction, conviction: Optional[Conviction] = None) -> PlanContext`. A `session_levels` section that is unavailable with reason `brief_row_missing` returns a context with `unavailable_reason="brief_row_missing"` before the close is checked; `read_stored_sides` raising gives `unavailable_reason="brief_plan_missing"`. Otherwise as today, `PlanContextUnavailable` on a missing close included.
  - `compute_persona_plans(ctx: PlanContext) -> list[PersonaPlan]`: `[]` for flat; three unavailable plans when `ctx.unavailable_reason` is set; three `orb_only` plans when the side has no trigger (as today, the reason and window read from the side record); otherwise three plans with `entry_zone = EntryZone(low=trigger, high=trigger)`, `stop` the stored stop's price or `None`, `targets` the stored targets' prices in stored order when `target_status == "ok"` and `[]` otherwise, all unrounded. `position_size_pct` is 0.0 while `ctx.conviction` is `None`.
  - `size_persona_plans(plans: list[PersonaPlan], ctx: PlanContext, conviction: Conviction) -> list[PersonaPlan]`: copies with `position_size_pct` from `_SIZE_BY_CONVICTION`, the catalyst damper and the two conservative gates as today, and the rationale's size clause.
  - `plan_unavailable_text(persona: str, reason: str) -> str`: `No {persona} plan: {reason}. No entry, stop or target is published.`
  - `compute_risk_metrics(entry_lo, entry_hi, stop: Optional[float], targets, direction, atr: Optional[float], sma_200=None, ftfc_score=None, invalidation_level=None) -> RiskMetrics`
  - Rationale of a published plan, one sentence: the trigger with its name, the stop with its name or "the brief's plan has no stop in its window", each target with its name or "no target is published: target_status <status>", then the size clause.

- [ ] **Step 1: Write the failing tests** in `tests/agents/test_trade_planner.py`. A helper `plans(ticker, basis=None, direction="short", conviction="low")` builds a bundle whose `session_levels` section holds the basis and whose `market` and `strat` sections come from `brief_row(ticker)`, then calls `context_from_bundle` and `compute_persona_plans`.
  - `TestBriefPlan::test_short_plans_are_the_stored_sides`, parametrised over the three tickers: every persona plan has `entry_zone.low == entry_zone.high ==` the entry, `stop ==` the stop and `targets ==` the targets of `EXPECTED_SHORT`. IWM: 275.86, 277.41, `[269.875]`.
  - `::test_personas_differ_only_in_size_and_rationale`: `model_dump()` of the three IWM plans, less `persona`, `position_size_pct` and `rationale`, are equal.
  - `::test_target_status_not_ok_publishes_no_target`: with `basis["short"]["target_status"] = "insufficient_history"`, `targets == []`, entry and stop unchanged, and `"insufficient_history" in rationale`.
  - `::test_no_target_is_a_multiple_of_the_stop_distance`: with every `target_*_r` value under `basis["params"]` set to 9.0, the IWM plans are unchanged; `targets[0]` is the `price` of `basis["short"]["targets"][0]`.
  - `::test_superseded_plan_is_gone`: the IWM neutral plan's stop is not 276.94 and its targets are not `[274.85, 274.34, 273.65]` (the values `origin/main` published, as literals).
  - `TestStoredSides::test_reads_the_records_as_written`: under stand-ins for `SessionLevels.from_basis` and `lib.strat_levels._assemble` that raise, `read_stored_sides(b).short is b["short"]`, `.long is b["long"]`, `.reference == b["reference"]`, `.atr == 4.87495`.
  - `::test_stored_pick_wins_over_a_rebuild`: on the IWM basis with `short["stop"] = None` and `short["targets"][0]["price"] = 270.00`: first, without stand-ins, `SessionLevels.from_basis(b)` gives `short.stop["price"] == 277.41` and `short.targets[0]["price"] == 269.875`; then, under the raising stand-ins, every persona plan has `stop is None` and `targets == [270.00]`.
  - `::test_basis_without_a_side_record`: `del b["short"]` makes `read_stored_sides` raise `StoredPlanMissing`, and every persona plan has null entry and stop, no targets and `"brief_plan_missing" in rationale`.
  - `TestMissingStop::test_risk_metrics_without_a_stop`: `compute_risk_metrics(275.86, 275.86, None, [269.875], "short", 4.87495, sma_200=250.0, ftfc_score=-0.75)` returns `stop_distance_atr`, `stop_distance_pct` and `invalidation_distance_atr` `None`, `target_r_multiples == []`, `entry_vs_sma200_pct == round((275.86 - 250.0) / 250.0 * 100, 3)` and `ftfc_aligned is True`.
  - Review Focus: `test_odd_stored_sides`: a short whose stored stop is below its entry, a target equal to the entry, four targets, a target with `price` null (left out, named in the rationale), and `atr` null (`stop_distance_atr` `None`, `stop_distance_pct` filled): none raises and each plan publishes the stored prices.
  - In `tests/agents/test_brief_is_the_source.py`: `test_missing_row_makes_every_persona_plan_unavailable`: the bundle of Task 3's missing-row case gives three plans with null `entry_zone` and `stop`, `targets == []` and `"brief_row_missing" in rationale`, under `raising_builders`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_trade_planner.py tests/agents/test_brief_is_the_source.py -q` (expect FAIL: `read_stored_sides` not defined; `TestMissingStop` fails with `TypeError` at `abs(entry_mid - stop)`).
- [ ] **Step 3: Implement.** `_plan` loses the entry buffers, the `persona_stop_price` call, the R multiples and the analog stretch; `select_trigger_and_regime`, `_params_unavailable_plan`, `_entry_text`, `_persona_target_keys` and the imports that only they use go with them. `risk_metrics` uses `stored.atr`. In the orchestrator, `report.level_basis` becomes the section's `level_basis` dict, and the headline is the neutral plan or null, null and `[]`; the portfolio manager's numbers at `:637-643` are no longer read.
- [ ] **Step 4: Run** the same command (expect all passed), then the affected existing set: `python3 -m pytest tests/lib/test_trade_planner.py tests/lib/test_trade_planner_distance_cap.py tests/lib/test_brief_planner_parity.py tests/lib/test_level_params_behaviour.py tests/lib/test_no_synthesized_levels.py tests/lib/test_orb_only_copy.py tests/agents tests/api -q`. Tests of the removed recipe (entry buffers, persona stops, R targets, the analog stretch, `ctx.levels`) are rewritten to the stored plan or removed, each named in the PR body with the reason; `tests/lib/test_brief_planner_parity.py` keeps its brief-side assertions and compares the planner's entry with the brief's stored trigger. Then `git diff origin/main -- lib/strat_levels.py | grep '^-[^-]'` on the working machine (expect no output; this is a check, not a test), and the render step.
- [ ] **Step 5: Commit:** `feat(insight): publish the brief's stored trigger, stop and targets as the plan`

### Task 5: The numeric risk rules, computed

Spec: Design 3, second and third bullets; decision 7; decision 11 (C2 takes the direction). Advances D5 (`TestRuleFlags`, the prompt clause) and D5b (`TestMissingStop`, its rule clauses). Open question 2 is answered before Step 1.

**Files:**
- Modify: `lib/agents/trade_planner.py`, `lib/agents/prompts.py` (`RISK_PERSONA_PROMPTS`, `:175-242`)
- Test: `tests/agents/test_trade_planner.py`

**Interfaces:**
- Consumes: `PersonaPlan.risk_metrics` (Task 4), `lib.agents.schema.RiskFlag`.
- Produces: `compute_rule_flags(plan: PersonaPlan, direction: Direction) -> tuple[list[RiskFlag], dict[str, str]]`: the flags, in the order N1, N2, N3, C1, C2, and the rules skipped for a null metric keyed by rule id.
  - N1, persona `neutral`, `warn`, when `stop_distance_atr < 1.0`: `Stop only {x:.2f}x ATR from entry midpoint; empirically -31.1pp win-rate`
  - N2, `neutral`, `warn`, when `target_r_multiples` has a first value under 1.5: `T1 only {r:.1f}R; empirically -18.8pp win-rate`
  - N3, `neutral`, `info`, when `ftfc_aligned is False`: `Direction conflicts FTFC alignment`
  - C1, `conservative`, `warn`, when `stop_distance_pct > 1.0`: `Stop {pct}% of price; empirically -24.9pp win-rate`
  - C2, `conservative`, `warn`, when `direction == "long"` and `entry_vs_sma200_pct > 10.0`: `Entry {pct}% above 200 SMA; empirically -21.8pp win-rate`
  - Skipped: with `plan.stop is None`, `{"N1": "stop_missing", "N2": "stop_missing", "C1": "stop_missing"}`; a null `ftfc_aligned` gives `{"N3": "ftfc_aligned_missing"}`; for a long, a null `entry_vs_sma200_pct` gives `{"C2": "entry_vs_sma200_pct_missing"}`. A plan with `risk_metrics is None` (orb_only, unavailable) gives `([], {})`.

- [ ] **Step 1: Write the failing tests** in `TestRuleFlags`. A helper `plan_with(**metrics)` builds a `PersonaPlan` holding a `RiskMetrics`.
  - `test_each_rule_one_step_either_side`, parametrised: N1 fires at `stop_distance_atr` 0.999 and not at 1.0; N2 at a first R of 1.499 and not 1.5, and not with an empty list; N3 on `False` and not `True`; C1 at 1.001 and not 1.0; C2 for a long at 10.001 and not 10.0. Each case asserts persona and severity.
  - `test_c2_follows_the_direction`: `entry_vs_sma200_pct` 12.0: `compute_rule_flags(p, "long")` holds C2, `compute_rule_flags(p, "short")` and `(p, "flat")` do not.
  - `test_iwm_fixture`: on the IWM neutral short plan of Task 4, the N1 message holds `0.32x ATR from entry` and `round(abs(275.86 - 277.41) / 4.87495, 2) == 0.32`; no N2 (`target_r_multiples[0] == pytest.approx(3.861, abs=0.001)`).
  - `test_qqq_and_spy_fixture`: N1 fires with `0.71x` and `0.22x` (decision 7).
  - `test_prompts_no_longer_state_the_rules`: none of the three risk prompts holds `stop_distance_atr < 1.0`, `target_r_multiples[0] < 1.5`, `stop_distance_pct > 1.0` or `entry_vs_sma200_pct > 10.0`; each holds `rule_flags`.
  - In `TestMissingStop`: `test_no_stop_gives_no_n1_n2_c1`: a plan with `stop=None` and the metrics of Task 4's case returns no N1, N2 or C1 and the skipped dict above.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_trade_planner.py -k "TestRuleFlags or TestMissingStop" -q` (expect FAIL: `compute_rule_flags` not defined).
- [ ] **Step 3: Implement** the function, and rewrite the three risk prompts: the five rules leave; each prompt says the platform computed the numeric rules and lists them under `rule_flags`, that the reviewer must not repeat or recompute them, and that any price it names must be one in `plan` or in `key_levels`. Rules C3 and C4 and the aggressive reviewer's brief stay.
- [ ] **Step 4: Run** the same command (expect all passed) and `python3 -m pytest tests/agents -q`, then the render step.
- [ ] **Step 5: Commit:** `feat(insight): compute the five numeric risk rules from the plan's metrics`

### Task 6: The critics see the published plan, and a flag cannot cite another price

Spec: Design 3 (the order, `_risk_payload`, `cited_prices_outside`, the withheld flag); decision 8. Closes D4, D5 and D6 (but for open question 1's clause).

**Files:**
- Modify: `lib/agents/orchestrator.py` (`_risk_payload` `:226-238`; `run_insight_pipeline` `:405-643`; `_PRICE_PATTERN` `:735`)
- Test: `tests/agents/test_agent_orchestrator.py`

**Interfaces:**
- Consumes: `context_from_bundle`, `compute_persona_plans`, `size_persona_plans`, `compute_rule_flags` (Tasks 4 and 5).
- Produces:
  - `cited_prices_outside(text: str, allowed: Sequence[float], *, entry: Optional[float] = None) -> list[str]`: the citations, as written, that match no allowed price. A citation is a number written with a `$`, or with a decimal part, or an integer within 20 percent of `entry` (no bare integer is read when `entry` is `None`). A number followed, with or without a space, by `%`, `x`, `R`, `ATR` or `pp` is not a price. A thousands comma inside a number is part of it. A citation matches an allowed price when that price, rounded half up to the citation's own number of decimals (`decimal.Decimal(str(price)).quantize(..., ROUND_HALF_UP)`), equals it.
  - `WITHHELD_FLAG_TEXT = "A {persona} reviewer's note was withheld: it cited a price that is not in the plan."`
  - `_risk_payload(bundle: dict, plan: Optional[PersonaPlan], direction: str, rule_flags: list[RiskFlag], key_levels: dict[str, float]) -> str`: JSON with `ticker`, `direction`, `plan` (`persona`, `entry_zone`, `stop`, `targets`, `regime`, `risk_metrics`, or `null` with `plan_unavailable` naming the reason), `rule_flags`, `key_levels`, `strat`, `catalysts`, `market`. No `trade_plan` key and nothing of `TraderOutput`.
  - The run's order: analysts, bull and bear, judge, trader, `key_levels = _derive_key_levels(bundle)`, plans from the trader's direction with no conviction, rule flags from the neutral plan, the three risk requests (each sent the plan of its own persona), the flag check, `blocked`, direction, and then, until Task 7 moves it, the portfolio manager and conviction as today, with `size_persona_plans` after conviction. A block makes the direction flat and `persona_plans` empty, as today.
  - `all_flags` is the rule flags followed by the critics' flags after the check. `failed_section_reasons["rule_flags"]` is the skipped rules as `N1: stop_missing; N2: stop_missing; C1: stop_missing`; `failed_section_reasons["risk_flags"]` is `withheld_off_plan_price: <count>` when a flag was withheld. Neither name joins `failed_sections`.
  - A critic flag is checked with `allowed` the plan's entry, stop and targets and every `key_levels` value, and `entry` the plan's entry. A flag with a citation outside keeps `persona` and `severity`, takes `WITHHELD_FLAG_TEXT`, and its original message is logged at warning level.
  - In `tests/agents/test_agent_orchestrator.py`: `_RecordingLLM(_MockLLM)`, which appends `(response_model, system, json.loads(user message))` to `self.requests` and takes optional overrides `trader`, `risk_flags` (per persona), `pm`; and a fixture `iwm_brief_bundle` that installs `insight_2026_11_16.brief_row("IWM")` for `BRIEF_ROW_SQL`, an options frame and the other readers, and returns `{"brief_tickers": frozenset({"IWM"}), "as_of": date(2026, 11, 16)}` for `run_insight_pipeline`.

- [ ] **Step 1: Write the failing tests** in a class `TestOneVoice`, each driving the real `run_insight_pipeline("IWM", **iwm_brief_bundle, snapshot=..., llm_factory=...)` with a trader stub that says short:
  - `test_critics_review_the_published_plan`: `len(mock.requests) == 14`; the three `RiskPersonaOutput` requests come after the `TraderOutput` request and before the `PortfolioManagerOutput` one; each payload's `plan` has `entry_zone == {"low": 275.86, "high": 275.86}`, `stop == 277.41`, `targets == [269.875]` and a `risk_metrics` with `stop_distance_atr`; each has `rule_flags` holding the N1 message; none has a `trade_plan` key, and the trader stub's own entry, stop and targets (`498.5`, `503.5`, `496.0`) appear nowhere in the payload text; for each persona, the published plan's `entry_zone`, `stop`, `targets` and `risk_metrics` equal the ones in that persona's request.
  - `test_computed_flags_are_published_and_cap_conviction`: critics return no flags; six analyst stubs say bearish, the trader's confidence is 0.72 and the row's `ftfc_score` is -0.75: `report.risk_flags` holds a `neutral` `warn` whose message holds `0.32x ATR from entry`, and `report.conviction != "high"`. A control in the same test, with `compute_rule_flags` replaced by a stand-in returning `([], {})`, gives `high`, so the computed flag is what caps it. (Moving the stop cannot serve as the control: see the note under "Where the spec and the code differ".)
  - `test_flag_naming_a_price_outside_the_plan_is_withheld`: the aggressive stub returns `warn` "Target 1 at 272.67 is too conservative": the published flag has persona `aggressive`, severity `warn` and message `A aggressive reviewer's note was withheld: it cited a price that is not in the plan.`; `failed_section_reasons["risk_flags"] == "withheld_off_plan_price: 1"`; the warn still counts (`conviction` is not `high`); a second run whose flags cite `277.41` and the value of a key level publishes both unchanged.
  - `test_price_citations_match_to_the_cent`, on the pure function with `allowed=[275.86, 277.41, 269.875]` and `entry=275.86`: `"276.94"` is outside; `"277.41"`, `"277.4"` and `"$277"` are inside; `"269.88"` is inside; `"$999"` is outside; `"0.32x ATR"`, `"1.5R"`, `"12.0%"` and `"4.87 ATR"` return `[]`.
  - Review Focus, `test_how_a_model_writes_a_number`: `"$1,234.50"` is one citation, outside; `"stop at 277.41."` is inside; `"275.86-277.41"` is two citations, both inside; `"0.75 x ATR"`, `"-24.9pp"`, `"11/16"`, `"200 SMA"` and `"RSI 70"` return `[]`; `"2026"` returns `[]`; `"over the last 250 sessions"` beside the IWM entry is read as a citation and reported outside (the spec's stated risk, pinned so a change to it is seen); an empty string and `None` return `[]`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_agent_orchestrator.py -k TestOneVoice -q` (expect FAIL: the risk payload holds `trade_plan`; `cited_prices_outside` not defined).
- [ ] **Step 3: Implement** the order, the payload, the function and the check. `_PRICE_PATTERN` is removed with its last reader in Task 7; until then it stays.
- [ ] **Step 4: Run** the same command (expect all passed) and `python3 -m pytest tests/agents tests/api -q`. `test_pipeline_end_to_end_green` and the other pipeline tests keep their 14-call and `failed_sections == []` assertions; any changed conviction expectation is recorded with the rule flag that caused it. Then the render step.
- [ ] **Step 5: Commit:** `fix(insight): send the risk reviewers the published plan and withhold off-plan prices`

### Task 7: One conviction, and narratives that agree with the plan

Spec: Design 4, first three bullets; decision 6. Closes D7 and D7b.

**Files:**
- Modify: `lib/agents/orchestrator.py` (`_portfolio_payload` `:241-265`; `run_insight_pipeline` `:453-482`, `:539-573`, `:645-712`; `_validate_thesis_consistency` and `_PRICE_PATTERN` `:721-822`, removed), `lib/agents/prompts.py` (`PORTFOLIO_MANAGER_PROMPT`, `:245-279`)
- Test: `tests/agents/test_agent_orchestrator.py`

**Interfaces:**
- Consumes: `cited_prices_outside` and the order of Task 6; `StoredSides.side` (Task 4) for the level names.
- Produces:
  - Conviction is computed before the portfolio manager: `_calibrate_conviction(direction=<the trader's, or flat on a block>, confidence_score=trader.confidence, analyst_agreement_count=..., ftfc_score=<the line at :554, unchanged>, risk_severities=[f.severity for f in all_flags])`. `report.confidence_score = trader.confidence`. Then `size_persona_plans`.
  - `_portfolio_payload(bundle, judge, *, direction, conviction, confidence_score, plan: Optional[PersonaPlan], risk_flags: list[RiskFlag], bull, bear) -> str`: JSON with `ticker`, `fixed` (`direction`, `conviction`, `confidence_score`, `plan`, `risk_flags`), `verdict`, `bull_case`, `bear_case`, `failed_sections`, `summaries`.
  - `PORTFOLIO_MANAGER_PROMPT`: the manager narrates fixed facts. Everything under `fixed` is decided and must not be restated differently; it writes `thesis`, `bull_case`, `bear_case` and `time_horizon`; it names no conviction level other than `fixed.conviction` and no price outside `fixed.plan` and `key_levels`. The conviction calibration paragraph leaves the prompt. `PortfolioManagerOutput` keeps its shape.
  - `narrative_conflicts(text: str, *, conviction: str, allowed: Sequence[float], entry: Optional[float]) -> list[str]`: `conviction:<level>` for each of low, medium, high other than `conviction` found in a sentence that holds the word conviction (case ignored), and `price:<citation>` for each result of `cited_prices_outside`.
  - `plan_sentence(direction: str, conviction: str, plan: Optional[PersonaPlan], side: Optional[dict], unavailable_reason: Optional[str]) -> str`: `Short, low conviction. Entry 275.86 (PMK_L), stop 277.41 (PQL), target 269.88 (PML).`, prices to two decimals rounded half up, each with its stored name; `no stop in the brief's window` in place of a missing stop; `targets 662.02 (<name>) and 637.01 (<name>)` for two; `no target` for none; `Flat, low conviction. No plan.` for flat; `Short, low conviction. No plan is published (<reason>).` for an unavailable or orb_only plan.
  - `thesis`, `bull_case` and `bear_case` are each checked on their own. A field with a conflict is replaced by `plan_sentence(...)`, its name joins `failed_sections` with `failed_section_reasons[name] = "narrative_conflict"`, and the original is logged at warning level. The portfolio manager's failure path (`:467-482`) is checked the same way.
  - `report.conviction`, `report.direction`, the plan and `report.confidence_score` never come from `pm`.

- [ ] **Step 1: Write the failing tests** in `TestOneVoice`:
  - `test_conviction_reaches_the_pm_and_the_header`: the `PortfolioManagerOutput` request's `fixed` holds `direction == "short"`, `conviction == report.conviction`, `plan.stop == 277.41`, `plan.targets == [269.875]` and the published flags; with a stub that answers `conviction="high"` and `direction="long"`, the report is still short with the computed conviction, and `report.confidence_score` is the trader's 0.72.
  - `test_thesis_naming_another_conviction_is_replaced`: computed low, stub thesis "Bearish structure, though the conviction is tempered to medium.": `report.thesis == "Short, low conviction. Entry 275.86 (PMK_L), stop 277.41 (PQL), target 269.88 (PML)."`, `"thesis" in report.failed_sections`, `report.failed_section_reasons["thesis"] == "narrative_conflict"`. A thesis saying "low conviction" and one that names no level are published unchanged.
  - `test_off_plan_price_in_each_narrative_field_is_replaced`, parametrised over `thesis`, `bull_case`, `bear_case` and over the citations `276.94` and `$999`: that field is the deterministic sentence and is in `failed_sections` with `narrative_conflict`; the two other fields are published as the stub wrote them and are not in `failed_sections`.
  - `test_narrative_citing_plan_prices_is_published`: the three fields citing `275.86`, `277.4` and `269.88` are published unchanged and `failed_sections` holds none of them.
  - Review Focus: `test_pm_failure_is_checked_too`: the portfolio-manager stub raising leaves a thesis that names no price outside the plan and a conviction equal to the header's.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_agent_orchestrator.py -k TestOneVoice -q` (expect the four new tests FAIL: the request has no `fixed` key; the thesis is published as written).
- [ ] **Step 3: Implement.** Remove `_validate_thesis_consistency`, `_PRICE_PATTERN` and the six `test_validate_thesis_*` tests of `tests/agents/test_agent_orchestrator.py:1137-1250`, whose function no longer exists (named in the PR body; `test_price_citations_match_to_the_cent` and `test_how_a_model_writes_a_number` replace them). Touching `:554` adds no change to it beyond keeping its `AUDIT-2026-05-13` marker.
- [ ] **Step 4: Run** the same command (expect all passed) and `python3 -m pytest tests/agents tests/api -q`, then the render step.
- [ ] **Step 5: Commit:** `fix(insight): fix conviction before the portfolio manager writes and replace a narrative that contradicts the plan`

### Task 8: Invalidation is the plan's stop; `trigger_high` and `trigger_low` leave the bundle

Spec: Design 4, last bullet; Design 1 (the removal, and `lib/agents/prompts.py:168`); Problem 1 row 4. Closes D8 and D5b.

**Files:**
- Modify: `lib/agents/orchestrator.py` (the report's `invalidation`, `:672`; `_derive_key_levels` `:1000-1009`; `_build_strat_snapshot` `:1140-1141`), `lib/agents/summarizers.py` (`summarize_strat_status`, `:480-481`, `:491-492`), `lib/agents/prompts.py` (`TRADER_PROMPT`, `:168-170`)
- Test: `tests/agents/test_agent_orchestrator.py`

**Interfaces:**
- Consumes: the neutral plan and its stored side (Tasks 4 and 7); `lib.strat_levels.orb_only_text` (`:1647`).
- Produces:
  - `NO_STOP_INVALIDATION = "The brief's plan has no stop in its window, so no invalidation price is given."`
  - `plan_invalidation(direction: str, plan: Optional[PersonaPlan], side: Optional[dict], unavailable_reason: Optional[str]) -> str`: `Stop 277.41 (PQL): the plan is invalid beyond it.` (two decimals, half up, the stop's stored name); `NO_STOP_INVALIDATION` for a trigger with no stop; `orb_only_text(side["reason"], direction, side.get("window"))` for an orb_only side; `""` for flat; `No plan is published (<reason>), so no invalidation price is given.` for an unavailable plan.
  - `report.invalidation = plan_invalidation(...)`; `pm.invalidation` and `trader.invalidation` are not published.
  - `TRADER_PROMPT` names the side's trigger: "Use the trigger of the side you choose, from session_levels.level_basis (long or short), and the ATR recorded there." The trader's own entry, stop and targets are still asked for by its schema and are not published.
  - `_trader_payload` (`lib/agents/orchestrator.py:205-223`) gains a `session_levels` key: the stored `long` and `short` side records and the basis ATR, taken from the bundle's `session_levels` section, or `{"available": false, "reason": <the section's reason>}` when that section is unavailable. Today the function sends only the verdict, strat, market and analysts, so without this the prompt would point the trader at data it is not given. The trader's direction and confidence still decide the published report, so it must see the sides it is choosing between.
  - The strat section, the legacy `Prev High` and `Prev Low` key levels and the built `StratSnapshot` no longer carry `trigger_high` or `trigger_low`. The two optional schema fields stay.

- [ ] **Step 1: Write the failing tests** in `TestOneVoice`:
  - `test_invalidation_is_the_plan_stop`: with a portfolio-manager stub whose `invalidation` is "A daily close above the trigger high of 282.2": `report.invalidation == "Stop 277.41 (PQL): the plan is invalid beyond it."` and `"282.2" not in report.invalidation`; with the stored short `trigger` set to `None`, `regime` `orb_only` and `reason` `no_levels`, it equals `orb_only_text("no_levels", "short", <the side's window>)` and holds no `$` and no number with two decimals; with a trader stub saying flat it is `""`.
  - `test_trader_is_sent_the_stored_sides`: a recording trader stub captures its request; the parsed payload's `session_levels.long` and `session_levels.short` equal the stored side records of the IWM fixture and `session_levels.atr` is the basis ATR; no key named `trigger_high` or `trigger_low` appears anywhere in the payload; with `session_levels` unavailable (`brief_row_missing`) the payload carries `{"available": false, "reason": "brief_row_missing"}` and the trader is still called.
  - `test_side_with_trigger_and_no_stop`: the IWM row with `level_basis["short"]["stop"] = None`: the headline and every persona plan have `entry_zone.low == 275.86`, `stop is None` and `targets == [269.875]`; each rationale holds "no stop in its window"; `report.invalidation == NO_STOP_INVALIDATION`; `failed_section_reasons["rule_flags"] == "N1: stop_missing; N2: stop_missing; C1: stop_missing"`; no risk flag is N1, N2 or C1; nothing raises.
  - `test_trigger_high_and_low_are_gone`: after a run on the builder path (`canned_bundle`), `"trigger_high" not in bundle["strat"]`, `report.strat_status.trigger_high is None`, and `report.key_levels` has no `Prev High` or `Prev Low`; `"trigger_high" not in TRADER_PROMPT`.
  - Review Focus: `test_invalidation_for_an_unavailable_plan`: the missing-row run gives `No plan is published (brief_row_missing), so no invalidation price is given.`
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_agent_orchestrator.py -k TestOneVoice -q` (expect the new tests FAIL: the invalidation is the stub's text).
- [ ] **Step 3: Implement.** The line beside the removed `:1140-1141`, `float(section.get("ftfc_score") or 0.0)` at `:1138`, is an existing fallback on an adjacent line: mark it `# AUDIT-2026-05-13: silent fallback` and do not change it.
- [ ] **Step 4: Run** the same command (expect all passed) and `python3 -m pytest tests/agents tests/api tests/gcp/test_insight_discord_push.py -q`. `tests/agents/test_agent_summarizers.py:132-133` and `test_derive_key_levels_legacy_fallback_when_no_levels_dict` change with the removal, each named in the PR body. Then the render step.
- [ ] **Step 5: Commit:** `fix(insight): build the invalidation from the plan's stop`

### Task 9: One options snapshot, max pain, and the largest open interest strike

Spec: Design 5; decision 9; Problem 1 row 6. Closes D9.

**Files:**
- Modify: `lib/agents/summarizers.py` (`summarize_options_flow`, `:655-738`), `lib/agents/orchestrator.py` (`_derive_key_levels`, `:1020-1024`; the comment at `:492`)
- Test: `tests/agents/test_agent_summarizers.py`, `tests/agents/test_agent_orchestrator.py`

**Interfaces:**
- Consumes: `lib.gamma.aggregate_by_strike(options: Sequence[dict]) -> list[dict]` (`lib/gamma.py:232`; each dict needs `type` `"call"` or `"put"`, `strike`, `open_interest`; it counts a null open interest as 0 at `:276`, which is why the null rows are filtered first) and `lib.gamma.max_pain(strikes) -> float | None` (`:852`). `_session_date_for` (`:502`).
- Produces, in the section `summarize_options_flow` returns:
  - the SQL selects `option_type, strike, expiration, volume, open_interest, implied_volatility, delta, snapshot_date, snapshot_ts`, keeps the `snapshot_date` choice of today's statement, and adds `snapshot_ts = (SELECT MAX(snapshot_ts) ...)` over that same date, in one statement; the outer `WHERE` keeps the `snapshot_date` equality so the index on `(ticker, data_source, snapshot_date DESC)` still applies. After the read the function keeps only the rows of the frame's latest `snapshot_ts`.
  - `max_pain`: `{"strike": float, "expiration": "YYYY-MM-DD", "snapshot_ts": ISO 8601}` or `None`, with `max_pain_reason` `no_expiration_on_or_after_session` or `no_open_interest` when `None`
  - `largest_oi_strike`: `{"strike": float, "scope": "all_expirations", "snapshot_ts": ISO 8601}` or `None`, with `largest_oi_strike_reason` `no_open_interest` when `None`
  - `oi_missing_contracts: int`, `snapshot_ts`, and `call_volume`, `put_volume`, `put_call_ratio`, `top_oi_strikes`, `vol_weighted_iv`, `contract_count` of the one snapshot. The key `max_pain_strike_proxy` is gone.
  - `_derive_key_levels` writes `Max Pain (exp MM/DD)` from `max_pain` and `Largest OI Strike (all exp)` from `largest_oi_strike`, each only when present, and no key named `Max Pain`.

- [ ] **Step 1: Write the failing tests.** A helper `chain(snapshots)` writes a frame with the nine columns. In a class `TestMaxPain`:
  - `test_max_pain_and_largest_oi_are_two_values`: session 2026-11-16; two snapshots (2026-11-13 20:55:30Z and 23:00:00Z) of two expirations (2026-11-16 and 2026-12-18). In the latest snapshot the 11/16 expiry's open interest is built so `lib.gamma.max_pain` of it is 280 (written out in the test and checked by calling `lib.gamma` directly on the same rows), and the 12/18 expiry holds a large open interest at 250, so the sum over both expiries peaks at 250; the earlier snapshot holds a larger open interest at 300. Assert `max_pain == {"strike": 280.0, "expiration": "2026-11-16", "snapshot_ts": <the 23:00Z instant>}`, `largest_oi_strike["strike"] == 250.0` with `scope == "all_expirations"`, and `300.0` is neither value nor in `top_oi_strikes`.
  - `test_sql_reads_one_snapshot`: the statement text holds `snapshot_ts`, `MAX(snapshot_ts)` and `expiration`.
  - `test_no_expiration_on_or_after_the_session`: every expiration before the session date: `max_pain is None`, `max_pain_reason == "no_expiration_on_or_after_session"`, and `largest_oi_strike` is still computed.
  - `test_null_open_interest`: three contracts of the 11/16 expiry with null open interest: both values equal those of the frame without the three rows, and `oi_missing_contracts == 3`; with every contract null, `max_pain is None` and `largest_oi_strike is None`, each with reason `no_open_interest`, neither is 250.0 nor any strike of the frame, and `_derive_key_levels` of a bundle holding that section writes neither key.
  - `test_proxy_key_is_gone`: `"max_pain_strike_proxy"` is not in the section, and no file under `lib/` holds the string (a scan of the directory's `.py` files, read from disk).
  - In `tests/agents/test_agent_orchestrator.py`: `test_derive_key_levels_names_max_pain_and_largest_oi`: a bundle whose options section holds both values gives `Max Pain (exp 11/16)` and `Largest OI Strike (all exp)` and no `Max Pain`.
  - Options edges: a nearest expiration holding calls only, and one holding a single strike, each return a max pain without raising; `snapshot_ts` given as strings and as `pd.Timestamp` give the same result.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_agent_summarizers.py -k TestMaxPain -q` (expect FAIL: `KeyError: 'max_pain'`).
- [ ] **Step 3: Implement.** Map `option_type` `calls` and `puts` to `call` and `put` for `aggregate_by_strike`. The two `.fillna(0)` pairs on volume and implied volatility (`:703-704`, `:720-721`) are existing fallbacks on adjacent lines: mark each `# AUDIT-2026-05-13: silent fallback` and do not extend them. Update `test_options_flow_ratios_and_top_oi` (`tests/agents/test_agent_summarizers.py:156-181`) and `test_derive_key_levels_extracts_strat_market_options` for the new columns and names, named in the PR body.
- [ ] **Step 4: Run** the same command (expect all passed) and `python3 -m pytest tests/agents -q`, then the render step.
- [ ] **Step 5: Commit:** `fix(insight): compute max pain for the nearest expiry of one snapshot and name the open interest peak`

### Task 10: Key level order

Spec: Design 6; decision 10. Closes D10.

**Files:**
- Modify: `lib/agents/schema.py` (`InsightReport`), `lib/agents/orchestrator.py` (new helper beside `_derive_key_levels`; the report), `gcp/insight_discord_push.py` (`_fmt_levels_field` `:140-152`, its call `:529`)
- Test: `tests/agents/test_agent_orchestrator.py`, `tests/gcp/test_insight_discord_push.py`

**Interfaces:**
- Produces:
  - `InsightReport.key_level_order: list[str] = []` and `InsightReport.key_level_order_basis: Optional[Literal["distance_from_reference", "price_desc_no_reference"]] = None`
  - `key_level_order(key_levels: dict[str, float], reference: Optional[float]) -> tuple[list[str], str]`: with a reference, every key by `abs(value - reference)`, nearest first, ties by name, and `"distance_from_reference"`; with none, every key by value, highest first, ties by name, and `"price_desc_no_reference"`.
  - The reference is `level_basis["reference"]` of the `session_levels` section when it is a number, else the `market` section's `close`, else `None`.
  - `_fmt_levels_field(key_levels: dict, order: Optional[list] = None) -> str`: with `order`, the keys it names that the dict holds, in that order, then every other key of the dict in dict order; without, dict order. Each line's format is unchanged. The call passes `r.get("key_level_order")`.

- [ ] **Step 1: Write the failing tests:**
  - `test_key_level_order` (module level): `key_level_order({"B": 280.0, "A": 270.0, "C": 275.5, "D": 276.5}, 276.0)` is `(["C", "D", "B", "A"], "distance_from_reference")` (C and D tie at 0.5 and sort by name); the IWM run of `iwm_brief_bundle` gives `sorted(report.key_level_order) == sorted(report.key_levels)` and `report.key_level_order_basis == "distance_from_reference"`, with the first key the one nearest `level_basis["reference"]`.
  - `TestOneVoice::test_key_levels_without_a_reference`: the real pipeline for IWM with the row missing and the options and gamma sections available: `report.key_levels` holds their levels, `report.key_level_order` lists them by price, highest first, ties by name, `report.key_level_order_basis == "price_desc_no_reference"`, and nothing raises.
  - `tests/gcp/test_insight_discord_push.py::test_levels_render_in_report_order`: `_fmt_levels_field({"EMA 20": 256.36, "SMA 200": 244.59, "Max Pain (exp 11/16)": 280.0}, ["Max Pain (exp 11/16)", "EMA 20", "SMA 200"])` renders the three lines in that order with the format of `test_fmt_levels_field_renders_dict`; without the second argument, dict order; and `format_report_embed` of a row whose report holds `key_level_order` renders the field in it.
  - Review Focus: `test_levels_field_with_a_stale_order`: an order naming a key the dict lacks, and omitting one it has, renders every key of the dict exactly once; a stored report with no `key_level_order` and a key named `Max Pain` renders as on `main`; `key_level_order({}, 276.0) == ([], "distance_from_reference")`.
- [ ] **Step 2: Run:** `python3 -m pytest tests/agents/test_agent_orchestrator.py -k "key_level" tests/gcp/test_insight_discord_push.py -k "levels" -q` (expect FAIL: `key_level_order` not defined; unexpected argument).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** `python3 -m pytest tests/agents tests/gcp/test_insight_discord_push.py -q` (expect all passed), then confirm on the working machine that the diff of `tests/gcp/test_insight_discord_push.py` holds added lines only (`git diff origin/main -- tests/gcp/test_insight_discord_push.py | grep '^-[^-]'` prints nothing; a check, not a test), then the render step.
- [ ] **Step 5: Commit:** `feat(insight): state the order of a report's key levels`

### Task 11: The API response test

Spec: D11b; AGENTS.md "Browser proof" (`:62-70`). Closes D11b.

**Files:**
- Create: `tests/api/test_insight_report_brief_plan.py`

**Interfaces:**
- Consumes: `_RecordingLLM`, `_mock_factory_ctor`, `seven_role_snapshot`, `iwm_brief_bundle` (Task 6); the `client`, `no_network`, `_Cursor` and `_Conn` pattern of `tests/api/test_insight_report_conservative_short.py:74-153`; `gcp.insight_pipeline_job._upsert_report(report, allow_update=False)` (`:373`); `GET /api/insights/report/{ticker}` (`platform/api/routers/insights.py:822`).

- [ ] **Step 1: Write the test file,** built as `test_insight_report_conservative_short.py` is: the real `run_insight_pipeline("IWM", as_of=date(2026, 11, 16), brief_tickers=frozenset({"IWM"}), ...)` with only the model stubbed (a short), `INSIGHT_AS_OF` unset so the row is `live`, the real `_upsert_report` into a captured connection, then the real router. `as_of` is passed so the session date, and with it the nearest expiration, does not move with the day the test runs.
  - `test_report_served_by_the_api_is_the_brief_plan`: the response's `report.persona_plans` each have `entry_zone == {"low": 275.86, "high": 275.86}`, `stop == 277.41`, `targets == [269.875]`; `report.invalidation == "Stop 277.41 (PQL): the plan is invalid beyond it."`; `report.brief_ref == {"analysis_date": "2026-11-16", "analysis_ts": <the fixture row's>, "run_kind": "live"}`; `report.key_levels` holds `Max Pain (exp 11/16)` and `Largest OI Strike (all exp)` and no `Max Pain`; `sorted(report.key_level_order) == sorted(report.key_levels)` with `key_level_order_basis == "distance_from_reference"`; `report.conviction` equals the conviction named in `report.thesis` when the thesis names one.
  - `test_missing_brief_row_is_served_as_unavailable`: the row frame empty: every persona plan has null `entry_zone` and `stop`, `targets == []` and `brief_row_missing` in its rationale; `report.failed_section_reasons["session_levels"] == "brief_row_missing"`; `report.brief_ref is None`; `report.entry_zone is None`.
  - Both run under `no_network`; the cursor raises on any SQL but the insert and the router's read.
- [ ] **Step 2: Run:** `python3 -m pytest tests/api/test_insight_report_brief_plan.py -q -s` (expect 2 passed; the red for D11b is this file run at Task 3's commit, where the response has none of the new fields, recorded in the PR body).
- [ ] **Step 3: Run:** `python3 -m pytest tests/api/test_openapi_snapshot.py -q` (expect passed with `platform/api/openapi.json` unchanged: `InsightReport` is not a component of it, the envelope's `report` is a plain object at `:7911-7973`). If it fails, run `python scripts/export_openapi.py`, commit the file and say so in the PR body.
- [ ] **Step 4: Commit:** `test(insight): prove the brief's plan in the report the API serves`

### Task 12: Evidence, records and the gate

Spec: D11; D12; Design 7; product-delivery Phase 4 and Phase 5. Closes D11 and D12. **The EXPLAIN in Step 2 is a production read: ask the owner once before running it.** Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them: the source hash covers those paths.

**Files:**
- Create: `tests/agents/test_insight_2026_11_16_evidence.py`
- Modify: `docs/product/02-FEATURE-CATALOG.md`, `docs/product/03-SITE-TRACEABILITY.md`, `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `docs/review-evidence/site-source-snapshot.json`, this plan (`pr:`)

- [ ] **Step 1: The side by side print.** `test_print_2026_11_16_side_by_side`, parametrised over the three tickers: the real `run_insight_pipeline` on the ticker's brief row with a recorded-response stub that replays the stored report's own model text (its direction and `confidence_score` as the trader's, its `risk_flags` as the critics' output by persona, its `thesis`, `bull_case`, `bear_case` and `invalidation` as the portfolio manager's). It prints, for the stored 13:46Z report and for the new one, the header (direction, conviction), the plan (entry, stop, targets), the invalidation, each flag and the key levels in order. It asserts only what D3 already pins (the new plan's entry, stop and targets for the stored direction's side) and that every published flag and narrative passes `cited_prices_outside` against the new plan. Run: `python3 -m pytest tests/agents/test_insight_2026_11_16_evidence.py -q -s` (expect 3 passed); paste the output in the PR body.
- [ ] **Step 2: EXPLAIN, read-only, on the owner's yes,** one dispatch of `./scripts/db_query_cr.sh` without `--commit` holding two statements written with literals for SPY and `snapshot_date < '2026-11-16'`: `EXPLAIN (ANALYZE, BUFFERS)` of Task 9's statement, and the same of the statement on `main` (`lib/agents/summarizers.py:676-688` as it stood before Task 9, copied into the PR body as text). Record the execution id and, for each, the rows read on the scan node and the rows returned (the spec expects 12,738 returned against 955,608). If the new statement reads far more rows than it returns, stop and report to the owner before the PR is marked ready (CLAUDE.md 3.8); it is not left as later work. Without the owner's yes this step is not run and the D11 box stays open, said so in the PR body.
- [ ] **Step 3: Run:** `make test` (expect no failure `origin/main` does not have), and `git diff --stat origin/main -- gcp/premarket_brief.py gcp/brief_explanations.py gcp/schema.sql gcp/deploy.sh lib/strat.py lib/gamma.py lib/level_calibration.py lib/indicators.py platform/api/routers` (expect empty).
- [ ] **Step 4: Commit:** `test(insight): print the 2026-11-16 reports beside the stored ones`
- [ ] **Step 5: Open the draft PR.** `git push -u origin feature/feat-insight-001-insight-one-plan-one-voice`. Body: the spec's and this plan's paths; the sixteen done_when items as `- [ ]` lines; `Red then green` for every new test; a Capacity section (Volume, Velocity, Wall-clock, Cost) with the Global Constraints figures and Step 2's measured ones; Step 1's output; D11b's pytest output; the list of every existing assertion changed or removed, by task; the three open questions and their answers; and a line that issue #867 is touched and whether it closes is the owner's call after the replay. Set `pr:` in this plan to the PR's number.
- [ ] **Step 6: Product record.** `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-INSIGHT-001` record (`:279`): append to the Status cell `; the insight report reads the brief's stored row and plan and recalculates neither, its risk reviews and narrative are checked against that plan, max pain is the nearest expiry's with the largest open interest strike named beside it, and key levels carry an order ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed)`; set Last reviewed to the date of the PR's head commit; add `tests/agents/test_trade_planner.py`, `tests/agents/test_brief_is_the_source.py` and `tests/api/test_insight_report_brief_plan.py` to Tests. `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-INSIGHT-001` (`:495`): append the PR to the `**PR lineage:**` line (`:497`), naming spec PR #1992 and issue #867. Commit both and the plan: `docs(product): record the brief-sourced insight plan under FEAT-INSIGHT-001`.
- [ ] **Step 7: Site note, step 1.** With a clean tree: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy its `source_identity_sha256`.
- [ ] **Step 8: Site note, step 2.** In `docs/product/03-SITE-TRACEABILITY.md` there is no `| FEAT-INSIGHT-001 | INSIGHTS-01 |` row today (the FEAT-INSIGHT-001 rows are INSIGHTS-04, INSIGHTS-07 and INSIGHTS-09, `:1330-1332`). Add one before `:1330`, in the form of its neighbours and touching no other byte: the new hash, then this change's prose (`GET /api/insights/report/{ticker}` returns a report whose plan is the brief row's stored trigger, stop and targets, with `brief_ref`, `key_level_order` and `key_level_order_basis`; `key_levels` holds `Max Pain (exp MM/DD)` and `Largest OI Strike (all exp)`; the router and the table are unchanged; tests named). Commit: `docs(site): note the brief-sourced plan on INSIGHTS-01`.
- [ ] **Step 9: Site note, steps 3 and 4.** Run `produce` again and commit `docs(site): regenerate the source snapshot`; then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0). If `origin/main` moved, update the branch, re-render and redo the four steps.
- [ ] **Step 10:** The render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass). Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports no `[P1]`, `[P2]` or `[P3]` line that `main` does not.
- [ ] **Step 11:** `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0). Push; tick each done_when box with its evidence; only then mark the PR ready. Gate files are not touched, so no red-team pass is owed.

## Close-out (not tasks; the owner's steps)

From the spec's Close-out. None is done by the implementer, none is a done_when box, and each, read-only ones included, starts on the owner's own yes.

1. Deploy: `./gcp/deploy.sh insights`, from `main` at or after the merge.
2. Replay 2026-11-16: the `gcloud run jobs execute insight-pipeline` command of the spec, with `INSIGHT_AS_OF=2026-11-16` and `INSIGHT_TICKERS=SPY,IWM,QQQ`. It writes three `replay` rows and their history rows and posts nothing. It needs the 11/16 `premarket_analysis` rows still `run_kind` live (see "Dependency on the brief spec").
3. The market check, ticker by ticker, recorded on the PR.
4. The browser runs against the deployed site for the insights report card.
5. On a `docs/` branch after the merge: `docs/product/08-AI-AGENT-ARCHITECTURE.md` (tier order, node contract), this plan's `status: done`, and the re-cut of PR #1831 (decision 1).

## Where the spec and the code differ (read on aa163a8e3)

- The spec names `tests/agents/test_trade_planner.py`; the planner's existing tests are `tests/lib/test_trade_planner.py`. This plan creates the file the spec names and leaves the other in place (Task 4 edits it).
- D12 speaks of the (FEAT-INSIGHT-001, INSIGHTS-01) note as existing; `docs/product/03-SITE-TRACEABILITY.md:1330-1332` holds no such row. Task 12 adds it.
- Design 5 cites the volume and IV fallbacks at `:704-705` and `:720-721`; the first pair is at `lib/agents/summarizers.py:703-704`.
- `summarize_options_flow`'s docstring (`lib/agents/summarizers.py:665-666`) says the table holds one snapshot per date; the spec's own reads show 77. Task 9 rewrites the docstring with the function.
- `RiskFlag` (`lib/agents/schema.py:131-138`) has no `tag`; the prompts' rules name one. Computed flags carry persona, severity and message only.
- The spec's task 3 says "`brief_missing` states"; D2 and Design 1 say `brief_row_missing`. This plan uses `brief_row_missing`.
- **N1 and C1 leave no stop that passes both on these tickers.** N1 warns under 1.0 ATR; C1 warns over 1.0 percent of price. On the spec's 11/16 figures one ATR is 1.77 percent of IWM's entry (4.87495 / 275.86), 2.4 percent of QQQ's (16.338 / 668.30) and 1.5 percent of SPY's (11.036 / 747.95), so a stop of 1.0 ATR or more trips C1 and a tighter one trips N1. A warn bars high conviction (`lib/agents/orchestrator.py:929-935`), so once the rules are computed truthfully, high is out of reach for all three at any stop distance, not only on 11/16. The spec's Risks name N1 alone. Thresholds are a non-goal here (decision 7); this is reported to the owner with the plan.
- D9 names `::test_null_open_interest` after `TestMaxPain` without a class; this plan puts it in `TestMaxPain`.

## What this plan did not verify

- The fixture's numbers: no production read was made for this plan. Task 1's first test checks the exported files against the spec's figures.
- Whether the stored report's `level_basis` equals the brief row's: Task 1 Step 2 compares them.
- The render step's command and the docs audit's baseline: copied from `docs/superpowers/plans/2026-11-16-feat-data-001-bar-misprint-flags.md`, not run here.
- How many existing tests change in Tasks 4 to 9: not counted; each task lists its own.
- The exact plan the new options statement gets from Postgres: Task 12 Step 2.
- Which date's watchlist membership a replay should use for the brief's list: `brief_tickers()` reads today's rows; the spec does not say.
- solyra's rendering of a null stop, an empty target list and the two new key level names: not opened (the spec's own open item).
