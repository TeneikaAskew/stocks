---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-16-feat-insight-001-conviction-reachable.md
branch: feature/feat-insight-001-conviction-reachable
pr: null
status: ready
---

# AI Insights: a conviction level that can be reached: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are named as the spec names them, V1 to V11.

**Goal:** Each numeric risk rule's line, unit and severity come from a rerunnable measurement on the brief's own plans and the choice recorded beside it; the conviction ladder is monotone; and every report stores the inputs its conviction was computed from.

**Architecture:** A pure module `lib/agents/rule_evidence.py` measures every brief side through `compute_risk_metrics` and summarizes each rule on a fixed grid with a session-clustered bootstrap and a holdout; its output is one JSON file and the markdown rendered from it. The PR stops as a draft at that point for the choices (decision 8). Then `RISK_RULES` in `lib/agents/trade_planner.py` holds the chosen rows with their evidence, `compute_rule_flags` reads it, `CONVICTION_LADDER` in `lib/agents/orchestrator.py` holds candidate A, and `InsightReport.conviction_inputs` records what the ladder read. Two tests tie the code to the recorded decision field for field.

**Tech Stack:** Python, numpy (bootstrap), pandas, pydantic, pytest, the stub `LLMClient` of `tests/agents/test_agent_orchestrator.py`, Starlette `TestClient`; production reads only through `./scripts/db_query_cr.sh` without `--commit`.

**Spec:** docs/superpowers/specs/2026-11-16-feat-insight-001-conviction-reachable.md (approved by the owner; decisions 1, 2, 3, 5, 7, 8 and 9 per their recommendations on 2026-11-16, decision 4 delegated to the build's stop in the middle on 2026-11-17; PR #2009, head 602730677, not yet on `main` when this plan was written).

## Start condition

The spec's precondition is the predecessor, `docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md`, built on `feature/feat-insight-001-insight-one-plan-one-voice` from the plan `docs/superpowers/plans/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md`, merged and deployed. When this plan was written that build had not been pushed: the remote branch (36a91999c) holds the plan only, and none of `compute_rule_flags`, `size_persona_plans`, `read_stored_sides` or the reordered conviction call exists on any pushed ref. Do not open the build branch until `git grep -n "def compute_rule_flags" origin/main -- lib/agents/trade_planner.py` prints a line. The spec (PR #2009) and this plan also merge first.

**Line numbers.** `file:line` references are read on `origin/main` 3a59299ba. The predecessor rewrites `lib/agents/trade_planner.py`, `lib/agents/orchestrator.py` and `lib/agents/prompts.py`, so every line in those three files moves: the names used here are the predecessor plan's (its Tasks 4 to 7 Interfaces blocks), and the first step of Task 1 re-finds each one on the real base. Where a done_when item says "fails on the predecessor's main", the red run is on the branch before the task's code step, recorded in the PR body.

## Global Constraints

- Branch `feature/feat-insight-001-conviction-reachable` from `origin/main` once the start condition holds. One PR, opened as a draft after Task 4, title `FEAT-INSIGHT-001: measure the risk rules and make conviction reachable`.
- SPY, QQQ and IWM only. No schema change (`conviction_inputs` is a field of the report JSON), no new model call, no Discord layout change, no new job, no production write. Not in the diff: `lib/strat_levels.py`, the brief, `_SIZE_BY_CONVICTION` (`lib/agents/trade_planner.py:140-144`), the conservative gates, `is_ftfc_aligned`'s thresholds, the FTFC weights, the blocking rule, the signal monitor.
- **No threshold is typed by the implementer.** Every number in `RISK_RULES` and `CONVICTION_LADDER` is copied from the `decision` block of `tests/agents/fixtures/conviction_evidence.json`, and V3's two tests enforce it.
- Values copied from the spec:
  - Outcome name `cross-fill-t1-v1` (the first-target surrogate); `outcome_r = eod_pnl_pct / stop_distance_pct`; win when `eod_pnl_pct > 0`; also the share of exits at the stop (`exit_reason == 'stop'`). Mean R is the primary measure.
  - Bootstrap: resample sessions, 10,000 draws, fixed seed, 95 percent. Win rates also carry a Wilson 95 percent range.
  - Floors: at least 30 filled sides from at least 20 sessions in each group.
  - Holdout: sessions sorted by date; the earliest two thirds fit, the latest third confirms.
  - Grid, and nowhere else: too tight in ATR 0.25, 0.5, 0.75, 1.0; too wide in ATR 1.0, 1.5, 2.0; too tight in percent 0.1, 0.25, 0.5; too wide in percent 0.5, 1.0, 1.5; N2 on `mean_target_r` at 1.0, 1.5, 2.0R (first target's multiple at the same points beside it, record only); above the 200 SMA at 5, 10, 15 percent (longs); N3 at its one setting, record only.
  - Present lines: N1 under 1.0 ATR; C1 over 1.0 percent; N2 under 1.5R; C2 long and over 10 percent above the 200 SMA; N3 FTFC not aligned, severity `info`.
  - Ladder candidate A (decision 5): a level is the highest whose floors are all met. `high`: agreement at least 4, FTFC aligned, 0 warns, confidence at least 0.7. `medium`: agreement at least 2, at most 1 warn, confidence at least 0.4. `low` otherwise, and always when flat or blocked.
  - `conviction_inputs` keys: `analyst_agreement_count`, `warn_count`, `block_count`, `confidence_score`, `ftfc_score`, `ftfc_aligned`, `rule_ids_fired`, `rule_table_version`, `ladder_version`.
  - Strings that leave `lib/agents/`: `-31.1pp`, `-24.9pp`, `-18.8pp`, `-21.8pp`.
  - V11's example: ATR 4.874951; IWM puts entry 275.86, stop 277.41, targets 274.64, 273.42, 272.20, 270.99, multiples 0.787, 1.574, 2.361, 3.142, mean 1.966; IWM calls entry 278.92, stop 275.86, targets 280.14, 281.36, 282.58, 283.79, mean 0.996.
- Constants this plan names (values are the spec's): `BOOTSTRAP_DRAWS = 10_000`, `BOOTSTRAP_SEED = 20261116`, `MIN_SIDES = 30`, `MIN_SESSIONS = 20`, `OUTCOME = 'cross-fill-t1-v1'`, `RULE_TABLE_VERSION = 'feat-insight-001.risk-rules.v1'`, `LADDER_VERSION = 'feat-insight-001.conviction-ladder.v1'`.
- No silent fallback (CLAUDE.md 3.7): a null stop, ATR, outcome, SMA or FTFC score stays null and is counted as unmeasurable, never 0; a null FTFC score in `conviction_inputs` is `null` and is read as not aligned.
- Tests are hermetic: no network, no database, no model, no git command against a second ref. The two production reads are files in the PR (the JSON), not test inputs fetched at run time.
- Production access: two read-only dispatches of `./scripts/db_query_cr.sh -f` without `--commit`, both in Task 4. **Ask the owner once, before Task 4, listing both SQL files; run nothing until they say yes.** No deploy, no replay, no job execution, no write.
- The render step. A task that changes a file under `gcp/` or `lib/` ends with
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect `1 passed`), and stages whichever of the three docs changed with the code.
- Capacity (CLAUDE.md rule 0; spec Design 5), for the PR body because the PR adds files under `gcp/queries/`: no Cloud Run job, schedule or model call added or changed; the measurement is two reads through the existing `db-query` job, one of about 525 brief rows (about 1,050 sides, live and replay) and one of about 600 stored reports, 5 to 15 s each as dispatched; the bootstrap is 10,000 draws over at most about 130 sessions per grid point, in memory, timed in Task 4 and stated; the report grows by one small JSON object; model spend none.
- Commits: conventional `type(scope): description`, imperative, no AI attribution. Every new test has a red then green record in the PR body.

## Choices this plan makes where the spec leaves one open or does not match the code

Reported to the owner with the plan.

1. **Decision 4 is chosen by a rule written here, before the measurement exists.** The owner delegated N1 and C1 to the build (2026-11-17); a choice made after seeing the table flatters it (spec Risks). So the build applies this procedure in Task 5 and records it as the reason:
   - Arrangements: `atr` (too tight and too wide both in ATR), `pct` (both in percent), `band_atr` and `band_pct` (the same two lines as one rule, `outside`, that counts as one warning).
   - In each arrangement each stop rule takes, among its grid points in that unit that pass (`rule_may_warn` true), the one with the most flagged filled sides; with none passing it is severity `info` at the grid point of that unit nearest 1.0 (ties to the larger point for too tight, the smaller for too wide), so it is shown and not counted (decision 3). A band takes the pair of grid points whose band row passes with the most flagged sides, else `info` at the pair those nearest-1.0 points make.
   - Drop an arrangement whose rows fail V5's check.
   - Choose the arrangement with the most `warn` rows; ties go to the one leaving more of the brief sides with no counted warning (the ceiling on `high`, Design 3); then `atr`, `pct`, `band_atr`, `band_pct` in that order (an ATR line treats the three tickers alike, Design 2).
   The decision block records `chosen_by: "build, under the owner's delegation of 2026-11-17"`, the date, the arrangement, and the rows and numbers that decided it.
2. **Tables 4 and 5 of Design 2 need the stored reports, which the side query does not read.** The ladder candidates (actual and A) and the outcome by level read `insight_reports_history`. The plan adds a second read-only file, `gcp/queries/conviction_report_evidence.sql`, next to the spec's `gcp/queries/conviction_rule_evidence.sql`. Both execution ids are in the evidence (V2 says "every read").
3. **The side's prices come from the structured columns** (`calls_trigger_price`, `calls_stop_price`, `calls_t1_price` to `calls_t3_price`, `atr14`, `sma200` and the put mirrors), as the spec's own counts did (Problem 2), and the outcome was scored on them. On a v3 or later row these targets are the gating targets, not the plan targets the predecessor publishes (`lib/strat_levels.py:1511-1514`, the comment for v3, read on 44dfa3d8c); the evidence file states the count of sides per rule version so this is visible, and close-out 5 reruns the measurement per rule version.
4. **Floors apply to the fitting sessions.** `rule_may_warn` is true when, on the fitting sessions, both groups meet 30 sides and 20 sessions and the range lies wholly below zero, and on the holdout sessions both groups hold at least one side and the range lies wholly below zero. The spec says the floors apply "in each group" and the holdout must agree; with 162 fills over 67 sessions the holdout third (about 22 sessions) cannot meet 20 sessions per group, so applying the floors there would make every rule "cannot be judged" by construction.
5. **A bootstrap draw in which a group is empty is skipped**; the range is over the kept draws, and `draws_kept` is recorded beside it.
6. **`_calibrate_conviction` keeps its parameters and returns the level.** Design 4 also says it "builds `conviction_inputs`"; a second return value would change its shape, so a sibling `_conviction_inputs(...)` builds the record from the same values and V7 proves the two agree by recomputing.
7. **The orchestrator's FTFC read keeps a null** (`lib/agents/orchestrator.py:554` on main, `float(... or 0.0)`), as V7 requires, and `is_ftfc_aligned` returns False for `None`. The predecessor left that line for PR #1831; this spec takes it. `lib/agents/trade_planner.py:641` (the planner's own read, which feeds the conservative gates) is not changed (Non-goals).
8. **The markdown is rendered from the JSON** by `render_evidence(doc) -> str`, whole, including "Owner decision"; `test_evidence_file_matches_its_json` asserts the committed file equals the rendering. Hand-written notes go in the PR body, not the file.
9. **Messages** (V8) are fixed templates: N1 `Stop {x:.2f}x ATR from entry` (percent unit: `Stop {x:.2f}% of price`), C1 `Stop {x:.2f}% of price` (ATR unit: `Stop {x:.2f}x ATR from entry`), a band `Stop {x:.2f}x ATR from entry, outside {lo:g} to {hi:g}x ATR` (or the percent form), N2 `Average target {mean:.2f}R over {n} target(s)`, C2 `Entry {pct:.1f}% above 200 SMA`, N3 `Direction conflicts FTFC alignment`; a `warn` adds `; flagged plans averaged {effect:+.2f}R against the rest (95% range {lo:+.2f}R to {hi:+.2f}R, n={n_flagged} and {n_unflagged}, {OUTCOME})`. Every R number carries its `R`, so the predecessor's `cited_prices_outside` never reads one as a price.

## done_when map

| done_when | What | Task |
|---|---|---|
| V1 | the measurement is code that can be run again | 1, 2, 3 |
| V2 | the evidence is a file a reviewer can open | 4 |
| V3 | the choice is on record and the code equals it | 5, 6, 8 |
| V4 | a rule counts only when its evidence allows it | 3, 6 |
| V5 | the stop rules cannot contradict each other | 7 |
| V6 | a more confident call never scores lower | 8 |
| V7 | the report says how its conviction was reached | 9 |
| V8 | no message quotes an effect the evidence does not hold | 6 |
| V9 | the changed API response is tested | 10 |
| V10 | the product record | 11 |
| V11 | N2 judges the average of the targets | 2, 6 |

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task named.

- **A side scored by the early scorer (2026-05-11.v1, no fill status) or never scored.** Counted under coverage, never as filled and never in an outcome. Task 2.
- **A short that wins.** `puts_eod_pnl_pct` is positive for a short that reached its target (read: `tests/gcp/test_premarket_playbook_resolver.py:141`, `test_put_triggers_hits_t1_realized_pnl_positive_for_short`), so a winning short has positive `outcome_r`. Task 2 pins it on a fixture side.
- **A report stored before this change** (no `conviction_inputs`) is served unchanged, and one whose stored `ftfc_score` is null recomputes to the same level. Tasks 9 and 10.
- **A table whose N1 and C1 lines are the same number in one unit** (tight under 1.0 ATR, wide over 1.0 ATR). A stop exactly at the line is free of both, so V5 holds; the check evaluates the lines themselves, not only points between them. Task 7.
- **A grid point that flags every filled side or none.** One group is empty: the row is `insufficient` with no effect number, not an error. Task 3.

## File map

| File | Change | Task |
|---|---|---|
| `gcp/queries/conviction_rule_evidence.sql` | new: one row per brief side, no threshold | 1 |
| `gcp/queries/conviction_report_evidence.sql` | new: one row per stored live report of the three tickers | 1 |
| `lib/agents/rule_evidence.py` | new: `measure_sides`, `summarize_rule`, `stop_candidates`, `ladder_candidates`, `outcome_by_level`, `build_evidence`, `render_evidence`, a `__main__` | 2, 3, 4 |
| `docs/audits/<run date>-conviction-rule-evidence.md`, `tests/agents/fixtures/conviction_evidence.json` | new: the evidence and the decision | 4, 5 |
| `lib/agents/trade_planner.py` | `RuleEvidence`, `RiskRule`, `RISK_RULES`, `RULE_TABLE_VERSION`, `rule_may_warn`, `rule_fires`, `stop_rules_leave_a_free_stop`; `compute_rule_flags` reads the table; `is_ftfc_aligned` (`:164-173` on main) reads `None` as not aligned | 3, 6, 7, 9 |
| `lib/agents/orchestrator.py` | `CONVICTION_LADDER`, `LADDER_VERSION`, `_calibrate_conviction` (`:887-942` on main), `_conviction_inputs`, the FTFC read (`:554` on main), the report build (`:645-670` on main) | 8, 9 |
| `lib/agents/schema.py` | `ConvictionInputs`, `InsightReport.conviction_inputs` (after `:312`); the `RiskMetrics` docstring (`:150-157`) | 6, 9 |
| `lib/agents/prompts.py` | any remaining effect figure (`:199`, `:205`, `:227`, `:233` on main, if the predecessor left one) | 6 |
| `tests/agents/test_rule_evidence.py` | new | 1, 2, 3, 4 |
| `tests/agents/test_trade_planner.py` | `TestRuleTable` | 3, 6, 7 |
| `tests/agents/test_agent_orchestrator.py` | `TestConvictionLadder` | 8, 9 |
| `tests/api/test_insight_report_conviction_inputs.py` | new | 10 |
| `docs/product/02-FEATURE-CATALOG.md`, `docs/product/12-PR-ISSUE-TRACEABILITY.md` | the close | 11 |

---

## Task 1: The two read-only queries

Spec: Design 1, "How it runs"; implementation item 1. Advances V1 (the side query) and V2 (the reads it names).

**Files:** Create `gcp/queries/conviction_rule_evidence.sql`, `gcp/queries/conviction_report_evidence.sql`; Test `tests/agents/test_rule_evidence.py` (new).

**Interfaces:** Produces the column contract every later task reads.
- Side query: `UNION ALL` of the calls half (`side = 'long'`) and the puts half (`side = 'short'`) of `premarket_analysis` for `ticker IN ('SPY', 'QQQ', 'IWM')`, columns `ticker, analysis_date, run_kind, side, trigger_price, stop_price, t1_price, t2_price, t3_price, atr14, sma200, ftfc_score, entry_status, eod_pnl_pct, exit_reason, outcome_resolver_version, rule_version` (`level_basis->>'rule_version'`), ordered by `analysis_date, ticker, side`. Live and replay rows both (decision 7 is applied in Python).
- Report query: `insight_reports_history` rows with `run_kind = 'live'` for the three tickers and `as_of` in the 180 days before the run, columns `ticker`, `session_date` (`(as_of AT TIME ZONE 'America/New_York')::date`, CLAUDE.md 3.9), `as_of`, `direction`, `conviction`, `confidence_score`, `ftfc_score` (`report->'strat_status'->>'ftfc_score'`), `warn_count` and `block_count` (counts over `jsonb_array_elements(report->'risk_flags')` by `severity`), ordered by `as_of`. The 180 days are `now() - interval '180 days'`, the only numeric literal allowed in it.

- [ ] **Step 1: Check the base.** Re-find on the real base each name this plan uses from the predecessor: `compute_rule_flags`, `compute_risk_metrics`, `size_persona_plans`, `_calibrate_conviction`'s call site, `is_ftfc_aligned`, and the predecessor's `iwm_brief_bundle` fixture and `_RecordingLLM`. Note any that differ from the predecessor plan in the PR body.
- [ ] **Step 2: Write the failing test** `test_queries_carry_no_threshold`: both files exist; the side query names every column above and holds no decimal literal (`re.search(r'\d+\.\d+', sql)` is None) and none of the grid's integers as a comparison operand; the report query's only numeric literal is `180`; neither holds `UPDATE`, `INSERT`, `DELETE` or `COMMIT` (case ignored).
- [ ] **Step 3: Run** `python3 -m pytest tests/agents/test_rule_evidence.py -q` (expect FAIL, file missing); write the two files; run again (expect pass).
- [ ] **Step 4: Render step, then commit** `feat(insight): add the read-only queries behind the risk rule evidence`.

## Task 2: Measuring each side

Spec: Design 1 ("Sample", "Outcome", "What the outcome is"), Design 6 ("What changes", the measurement bullet). Advances V1 (`measure_sides`) and V11 (the measure).

**Files:** Create `lib/agents/rule_evidence.py`; Test `tests/agents/test_rule_evidence.py`.

**Interfaces:**
- Consumes: `lib.agents.trade_planner.compute_risk_metrics` as the predecessor leaves it (`(entry_lo, entry_hi, stop: Optional[float], targets, direction, atr: Optional[float], sma_200=None, ftfc_score=None, invalidation_level=None)`), looked up on the module at call time (`trade_planner.compute_risk_metrics(...)`), never bound by `from ... import`, so a stand-in is seen.
- Produces: `measure_sides(rows: Iterable[Mapping]) -> list[dict]`, one dict per input row with `ticker`, `session` (`date`), `side`, `run_kind`, `rule_version`, `coverage` (`filled`, `gap_through`, `not_triggered`, `invalid_stop`, `scored_no_status` for a row resolved by `2026-05-11.v1`, `unscored` for a row with no resolver version), `stop_distance_atr`, `stop_distance_pct`, `first_target_r`, `mean_target_r` (mean of `target_r_multiples` over every target the side holds, None with no target or no stop), `entry_vs_sma200_pct`, `ftfc_aligned`, `outcome_r`, `won`, `stopped_out`, and `unmeasurable` (the list of measures that are None and why). Entry is the trigger (`entry_lo = entry_hi = trigger_price`), targets are `t1_price` to `t3_price` that are not null, direction `long` or `short`. Outcome fields are None unless `coverage == 'filled'`.

- [ ] **Step 1: Write the failing tests:**
  - `test_measure_calls_the_planners_formula`: with `trade_planner.compute_risk_metrics` replaced by a stand-in that raises, `measure_sides([<one filled side>])` raises.
  - `test_measures_of_a_filled_side`: an IWM short with trigger 275.86, stop 277.41, targets 274.64, 273.42, 272.20, ATR 4.874951, SMA 250.0, `eod_pnl_pct` 0.44, `entry_status` `filled`, `exit_reason` `t1`: `stop_distance_atr == round(1.55 / 4.874951, 3)`, `first_target_r == 0.787`, `mean_target_r == pytest.approx((0.787 + 1.574 + 2.361) / 3, abs=1e-3)`, `outcome_r == pytest.approx(0.44 / <its stop_distance_pct>)`, `won is True`.
  - `test_null_inputs_stay_null`: a null stop gives `stop_distance_atr`, `stop_distance_pct`, `first_target_r`, `mean_target_r` and `outcome_r` None, each named in `unmeasurable`, and no field equal to 0; the same for a null ATR (only the ATR measure), a null SMA (`entry_vs_sma200_pct`), a null FTFC score (`ftfc_aligned`).
  - `test_coverage_not_outcome`: `gap_through`, `not_triggered`, `invalid_stop`, a `2026-05-11.v1` row and an unscored row each have the named `coverage` and every outcome field None.
  - Review Focus: `test_a_winning_short_is_positive`: a short filled at 275.86 that exited at T1 with `eod_pnl_pct` positive has positive `outcome_r`.
- [ ] **Step 2: Run** (expect FAIL, module missing), implement, run again (expect pass).
- [ ] **Step 3: Render step, then commit** `feat(insight): measure each brief side through the planner's own formula`.

## Task 3: Summaries, the bootstrap and the decision rule

Spec: Design 1 ("Unit and range", "Grid", "Holdout"), Design 2 (tables 2 and 3), Design 4 (the decision rule). Advances V1 (`summarize_rule`) and V4 (`rule_may_warn`).

**Files:** Modify `lib/agents/rule_evidence.py`, `lib/agents/trade_planner.py`; Test `tests/agents/test_rule_evidence.py`, `tests/agents/test_trade_planner.py`.

**Interfaces:**
- Produces, in `lib/agents/trade_planner.py`: `RuleEvidence`, a frozen dataclass with `outcome`, `execution`, `measured_on`, `rule_versions`, `n_flagged`, `n_unflagged`, `sessions_flagged`, `sessions_unflagged`, `effect_r`, `range_r` (a `(lo, hi)` pair), `holdout_n_flagged`, `holdout_n_unflagged`, `holdout_effect_r`, `holdout_range_r`, `decided_by`, `decided_on`; and `rule_may_warn(evidence: Optional[RuleEvidence], *, min_sides: int = MIN_SIDES, min_sessions: int = MIN_SESSIONS) -> bool` (Choice 4; None gives False).
- Produces, in `lib/agents/rule_evidence.py`:
  - `RuleSpec(id, metric, comparison, threshold, direction)` with `comparison` in `lt`, `gt`, `outside` (threshold a `(lo, hi)` pair) or `is_false`; `flags(side: dict, rule: RuleSpec) -> Optional[bool]` (None when the metric is None).
  - `GRID: tuple[RuleSpec, ...]`, the grid of Global Constraints with ids `N1_atr`, `N1_pct`, `C1_atr`, `C1_pct`, `N2_mean`, `N2_first` (record only), `C2`, `N3` (record only), and the bands `BAND_atr` and `BAND_pct` over every same-unit pair of a too-tight and a too-wide point with the tight point not above the wide one.
  - `summarize_rule(sides: list[dict], rule: RuleSpec, *, min_sides=MIN_SIDES, min_sessions=MIN_SESSIONS, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED) -> dict` over live filled sides only: `n_flagged`, `n_unflagged`, `sessions_flagged`, `sessions_unflagged`, `mean_r_flagged`, `mean_r_unflagged`, `effect_r` (flagged minus unflagged), `range_r`, `draws_kept`, `win_rate_flagged` and `_unflagged` with Wilson ranges, `stop_exit_share_flagged` and `_unflagged`, the same under `holdout`, `unmeasurable`, and `verdict` in `passes`, `flagged_better`, `no_clear_effect`, `insufficient`. Under the floor on the fitting sessions: `verdict == 'insufficient'` and `effect_r`, `range_r` None. The bootstrap: `numpy.random.default_rng(seed)`; each draw takes as many sessions as the subset holds, with replacement, and recomputes both group means over the drawn sessions' sides; Choice 5 for an empty group; `numpy.percentile(..., [2.5, 97.5])`.
  - `rule_verdict(rows: list[dict], present: RuleSpec) -> str`, Design 4's table: `keep`, `change_threshold`, `change_unit`, `owner_chooses`, `cannot_be_judged`, `drop`.

- [ ] **Step 1: Write the failing tests:**
  - `test_summarize_rule_on_twelve_sides`: four sessions of three live filled sides each, one flagged side at `outcome_r` -0.4 and two unflagged at 0.1 and 0.3 per session, so every draw gives -0.6. With `min_sides=2, min_sessions=2`: `n_flagged == 4`, `n_unflagged == 8`, `sessions_flagged == sessions_unflagged == 4`, `effect_r == pytest.approx(-0.6)`, `range_r == pytest.approx((-0.6, -0.6))`, holdout (the last two sessions) the same, `verdict == 'passes'`; two calls return equal dicts. With the default floors: `verdict == 'insufficient'`, `effect_r is None`, `range_r is None`.
  - `test_replay_and_unfilled_sides_are_not_in_the_outcome`: adding replay sides and `gap_through` sides to the same fixture changes no count.
  - Review Focus `test_a_point_that_flags_every_side`: every side flagged: `verdict == 'insufficient'`, no exception.
  - `test_rule_verdict_follows_design_4`, one case per row of Design 4's table, built from hand-made row dicts.
  - In `tests/agents/test_trade_planner.py`, `TestRuleTable::test_rule_may_warn`: true for floors met and both ranges wholly below zero; false when either range touches zero, when a fitting group has 29 sides or 19 sessions, when a holdout group is empty, and for None.
- [ ] **Step 2: Run** `python3 -m pytest tests/agents/test_rule_evidence.py "tests/agents/test_trade_planner.py::TestRuleTable" -q` (expect FAIL), implement, run again (expect pass).
- [ ] **Step 3: Render step, then commit** `feat(insight): summarize each risk rule with a session bootstrap and a holdout`.

## Task 4: The run and the evidence file; the PR stops here

Spec: Design 2, Design 3 ("How the stored reports would have looked", "Do the levels separate outcomes"), decision 8. Closes V2.

**Files:** Modify `lib/agents/rule_evidence.py`; Create `docs/audits/<run date>-conviction-rule-evidence.md`, `tests/agents/fixtures/conviction_evidence.json`; Test `tests/agents/test_rule_evidence.py`.

**Interfaces:** Produces `build_evidence(side_rows, report_rows, *, executions: dict[str, str], run_date: date) -> dict` and `render_evidence(doc: dict) -> str`, and `python -m lib.agents.rule_evidence --sides <csv> --reports <csv> --side-execution <id> --report-execution <id> --run-date YYYY-MM-DD --out-json <path> --out-md <path>`. The JSON keys: `outcome` (`cross-fill-t1-v1`), `reads` (file, execution id, run date for each query), `rule_versions` (sides per rule version, `none recorded` for a null), `sample` (Table 1, live and replay apart), `grid` (Table 2, one row per `GRID` entry with its `summarize_rule` dict), `stop_candidates` (Table 3: each arrangement of Choice 1 with its rows, its flagged count on all brief sides per ticker, and whether it passes V5's check), `ladder_candidates` (Table 4: actual, A as bounds, B and C `not measurable from stored data`, and per arrangement the brief sides with no counted warning), `outcome_by_level` (Table 5: per stored level, filled sides of the matching direction, wins, Wilson range, mean R), `sides` (the measured sides, so the file can be summarized again offline), and later `decision`. Every outcome column heading in the markdown names `cross-fill-t1-v1`; every cell is a number with its n, `insufficient`, or `not measurable from stored data`.

- [ ] **Step 1: Write the failing tests** `test_evidence_file_matches_its_json` (exactly one `docs/audits/*-conviction-rule-evidence.md`; it equals `render_evidence(json.load(<the JSON>))`) and `test_every_outcome_names_the_surrogate` (every table heading that holds `R` or `win` in the rendered markdown holds `cross-fill-t1-v1`; neither file holds `thirds`, `four-quarter`, `plan_r` or `exit plan` beside an outcome). Add `test_build_evidence_on_fixture_rows` on a small typed fixture of side and report rows, so the code is tested before any production read.
- [ ] **Step 2: Run** (expect FAIL), implement `build_evidence`, `render_evidence` and the command, run `test_build_evidence_on_fixture_rows` (expect pass).
- [ ] **Step 3: Ask the owner once** (Global Constraints) to run the two reads. On yes: `./scripts/db_query_cr.sh -f gcp/queries/conviction_rule_evidence.sql` and `./scripts/db_query_cr.sh -f gcp/queries/conviction_report_evidence.sql`; note each execution id; copy each `result_000.csv` from `gs://${PROJECT_ID}-trading-data/query-results/<exec>/` (CLAUDE.md, Database access) to a scratch directory outside the repo.
- [ ] **Step 4: Run** the command on the two CSVs with today's date and both ids, writing the two files; time it (Capacity). Run `python3 -m pytest tests/agents/test_rule_evidence.py -q` (expect all pass).
- [ ] **Step 5: Render step, commit** `docs(audit): measure the risk rules on the brief's own plans`, push with `git push -u origin feature/feat-insight-001-conviction-reachable`, open the **draft** PR (body: the spec's and this plan's paths, V1 to V11 as `- [ ]` lines, the five tables, the two execution ids, the timing, this plan's "Choices", and the Choice 1 procedure applied to the table with its outcome), and set `pr:` in this plan to its number in the next commit.
- [ ] **Step 6: Stop.** Decision 8: the PR waits as a draft for the owner's choices on every rule other than N1 and C1 (each per Design 4's table: a mechanical verdict is confirmed, `owner_chooses` rows are chosen) and the confirmation of ladder candidate A. Nothing after this step starts before the owner's reply on the PR.

## Task 5: The decision block

Spec: Design 4 (decision rule), decisions 3, 4 and 5; Authority ("Decision 4, settled 2026-11-17"). Advances V3 (the record).

**Files:** Modify `tests/agents/fixtures/conviction_evidence.json`, `docs/audits/<run date>-conviction-rule-evidence.md` (re-rendered); Test `tests/agents/test_rule_evidence.py`.

**Interfaces:** Produces the `decision` block: `rules`, one entry per rule id of `RISK_RULES` (`N1`, `C1` or the one band id, `N2`, `C2`, `N3`) with `metric`, `unit`, `comparison`, `threshold`, `severity`, `direction`, `persona`, the grid row it came from (or `present line, cannot be judged`), `verdict`, `chosen_by`, `chosen_on`; `ladder` with `candidate: "A"`, the levels and floors of Global Constraints, `chosen_by: "owner"`, `chosen_on: "2026-11-16"`; `rule_table_version`; `ladder_version`. `render_evidence` renders it under the heading `Owner decision`.

- [ ] **Step 1: Write the failing test** `test_decision_is_complete`: the block exists; each rule entry has every field, a `chosen_by` and an ISO `chosen_on`; N1 and C1 (or the band) name `chosen_by` `build, under the owner's delegation of 2026-11-17` and the Choice 1 arrangement; a `warn` entry's grid row has `verdict == 'passes'`; a row whose verdict is `cannot_be_judged` is `info`.
- [ ] **Step 2: Fill** the block: N1 and C1 by Choice 1, every other rule as the owner's reply on the PR says, with the reply's date and the owner as chooser; quote the reply in the PR body. Re-render the markdown.
- [ ] **Step 3: Run** `python3 -m pytest tests/agents/test_rule_evidence.py -q` (expect all pass), then commit `docs(audit): record the risk rule and ladder choices`.

## Task 6: The rule table

Spec: Design 4 ("Code"), Design 6 ("What changes"). Closes V4, V8, V11; advances V3 (`test_table_equals_the_decision_record`).

**Files:** Modify `lib/agents/trade_planner.py` (`compute_rule_flags` and the new table), `lib/agents/schema.py` (`RiskMetrics` docstring, `:150-157` on main), `lib/agents/prompts.py` (any effect figure the predecessor left); Test `tests/agents/test_trade_planner.py`.

**Interfaces:**
- Consumes: `RuleEvidence`, `rule_may_warn` (Task 3); the decision block (Task 5).
- Produces: `RiskRule`, a frozen dataclass with `id`, `persona`, `metric` (`stop_distance_atr`, `stop_distance_pct`, `mean_target_r`, `entry_vs_sma200_pct`, `ftfc_aligned`), `unit`, `comparison`, `threshold`, `severity`, `direction` (`both` or `long`), `evidence: Optional[RuleEvidence]`; `RISK_RULES: tuple[RiskRule, ...]`, in the order N1, N2, N3, C1, C2 (a band takes N1's place and C1 leaves); `RULE_TABLE_VERSION`; `rule_fires(rule: RiskRule, metrics: RiskMetrics, direction: str) -> Optional[bool]`. `compute_rule_flags(plan, direction)` keeps the predecessor's signature and return `(flags, skipped)`, holds no number of its own, computes `mean_target_r` from `plan.risk_metrics.target_r_multiples` where it applies N2 (never `[0]`), and builds each message by Choice 9. The skipped dict keeps the predecessor's keys and reasons, with N2 also skipped as `target_missing` when the plan holds no target.

- [ ] **Step 1: Write the failing tests** in `TestRuleTable`:
  - `test_table_equals_the_decision_record`: load the JSON; every `RISK_RULES` entry equals its `decision.rules` entry field for field (evidence included); with the `decision` key removed from a copy the comparison fails (`pytest.raises(KeyError)` on the loader).
  - `test_each_rule_one_step_either_side`, parametrised from `RISK_RULES` (never typed): the step is 0.001 in the rule's metric; for `lt` the rule fires at `threshold - 0.001` and not at `threshold`; for `gt` at `threshold + 0.001` and not at it; for `outside` beyond each edge and not at either; `is_false` on False and not True.
  - `test_the_table_is_read`: replacing one rule's threshold under monkeypatch moves the step at which it fires.
  - `test_every_warn_rule_passes_its_own_evidence`: `rule_may_warn(r.evidence)` for each `warn` rule; and a copy of the table with a `warn` rule whose evidence range touches zero makes the same assertion fail.
  - `test_an_info_rule_is_published_and_not_counted`: an `info` flag appears in the flags with its number in the message and `_calibrate_conviction` with that flag's severity gives the level it gives with none.
  - `test_n2_reads_the_average_of_the_targets` (V11's values): with N2's threshold set to 1.5 under monkeypatch, the IWM puts plan gives multiples `[0.787, 1.574, 2.361, 3.142]` from `compute_risk_metrics`, mean 1.966, no N2 flag; the IWM calls plan gives mean 0.996 and an N2 flag whose message holds `Average target 1.00R over 4 target(s)`; one target gives a mean equal to its multiple; no target or a null stop gives no N2 and N2 in the skipped dict; `ast` over `lib/agents/` finds no comparison whose operand subscripts `target_r_multiples` with `0`.
  - `test_messages_cite_only_recorded_effects`: no file under `lib/agents/` holds `-31.1pp`, `-24.9pp`, `-18.8pp` or `-21.8pp`; each `warn` message holds its rule's `effect_r`, `n_flagged`, `n_unflagged` and `cross-fill-t1-v1`; an `info` message holds none of them.
- [ ] **Step 2: Run** `python3 -m pytest "tests/agents/test_trade_planner.py::TestRuleTable" -q` (expect FAIL: `RISK_RULES` undefined).
- [ ] **Step 3: Implement** the table from the decision block (copy, do not type a new number), `rule_fires`, `compute_rule_flags` on the table, the messages, and remove the four figures from the `RiskMetrics` docstring (its rule list becomes a pointer to `RISK_RULES`) and from any prompt that still holds them.
- [ ] **Step 4: Run** the Step 2 command (expect all pass), then `python3 -m pytest tests/agents tests/api -q`. The predecessor's `TestRuleFlags` assertions that typed a threshold or a figure are changed to read the table; each changed assertion is named in the PR body.
- [ ] **Step 5: Render step, then commit** `feat(insight): read the risk rules from a table backed by their evidence`.

## Task 7: The stop rules leave a free stop

Spec: Design 4 ("For N1 and C1 the chosen rows must also pass V5"). Closes V5.

**Files:** Modify `lib/agents/trade_planner.py`; Test `tests/agents/test_trade_planner.py`.

**Interfaces:** Produces `stop_rules_leave_a_free_stop(rules: Sequence[RiskRule], atr_pct: float) -> bool`: true when some stop distance, in percent of price, makes no rule on `stop_distance_atr` or `stop_distance_pct` fire, whatever its severity. Candidates are every threshold of those rules converted to percent at `atr_pct` (an ATR threshold times `atr_pct`), the midpoints between consecutive candidates, and one point below the smallest and above the largest. Task 4's `stop_candidates` uses the same function.

- [ ] **Step 1: Write the failing test** `test_some_stop_is_free_of_stop_warnings`: for every ATR from 0.5 to 3.0 percent in steps of 0.05, `stop_rules_leave_a_free_stop(RISK_RULES, atr)`; and on a table of the two present lines (N1 `lt` 1.0 in ATR, C1 `gt` 1.0 in percent) it is false for every ATR above 1.0 percent and true at and below it. Review Focus: a table with tight `lt` 1.0 ATR and wide `gt` 1.0 ATR is true at every ATR (the stop at 1.0 ATR is free).
- [ ] **Step 2: Run** (expect FAIL), implement, run again (expect pass).
- [ ] **Step 3: Render step, then commit** `test(insight): prove some stop is free of every stop rule`.

## Task 8: A monotone ladder

Spec: Design 3 (candidate A), decision 5. Closes V6; advances V3 (`test_ladder_equals_the_decision_record`).

**Files:** Modify `lib/agents/orchestrator.py` (`_calibrate_conviction`, `:887-942` on main); Test `tests/agents/test_agent_orchestrator.py`.

**Interfaces:** Produces `LadderLevel`, a frozen dataclass `(level, min_agreement, ftfc_aligned_required, max_warn, min_confidence)`; `CONVICTION_LADDER: tuple[LadderLevel, ...]` from `high` down to `medium`; `LADDER_VERSION`. `_calibrate_conviction(*, direction, confidence_score, analyst_agreement_count, ftfc_score: Optional[float], risk_severities)` keeps its parameters and returns `low` for flat or any `block`, else the first level of `CONVICTION_LADDER` whose floors are all met, else `low`; it counts only `warn`.

- [ ] **Step 1: Write the failing tests** in `TestConvictionLadder`:
  - `test_ladder_equals_the_decision_record`: `CONVICTION_LADDER` and `LADDER_VERSION` equal `decision.ladder` field for field; with `decision` removed the comparison fails.
  - `test_monotone`: over confidence 0.00 to 1.00 in steps of 0.01, agreement 0 to 6, warns 0 to 4, FTFC aligned or not (scores 0.8 and -0.8 for a long), raising confidence, raising agreement, aligning FTFC or removing one warning never lowers the level (`low < medium < high`).
  - `test_flat_and_block_stay_low`: flat at confidence 1.0 and agreement 6 is `low`; a `block` is `low`.
  - `test_the_ceiling_is_gone`: agreement 4, FTFC 0.8, one `warn`: 0.70 and 0.71 both give `medium` (on the predecessor's main 0.71 gives `low`; the red run records it).
- [ ] **Step 2: Run** `python3 -m pytest tests/agents/test_agent_orchestrator.py -k TestConvictionLadder -q` (expect FAIL), implement, run again (expect pass), then `python3 -m pytest tests/agents tests/api -q` with any changed conviction expectation named in the PR body.
- [ ] **Step 3: Render step, then commit** `fix(insight): make conviction the highest level whose floors are met`.

## Task 9: The report stores its conviction inputs

Spec: Design 3 ("Stored going forward"). Closes V7.

**Files:** Modify `lib/agents/schema.py`, `lib/agents/orchestrator.py` (the FTFC read, `:554` on main; the report build, `:645-670` on main), `lib/agents/trade_planner.py` (`is_ftfc_aligned` reads None as False); Test `tests/agents/test_agent_orchestrator.py`.

**Interfaces:** Produces `ConvictionInputs(BaseModel)` with the nine keys of Global Constraints (`ftfc_score: Optional[float]`, `ftfc_aligned: bool`, `rule_ids_fired: list[str]`, the two versions as `str`), `InsightReport.conviction_inputs: Optional[ConvictionInputs] = None`, and `_conviction_inputs(*, direction, confidence_score, analyst_agreement_count, ftfc_score, risk_severities, rule_ids_fired) -> ConvictionInputs`. The run calls both with the same values; `rule_ids_fired` is the ids of the computed flags published.

- [ ] **Step 1: Write the failing tests** in `TestConvictionLadder`:
  - `test_inputs_are_stored`: the real `run_insight_pipeline` on the predecessor's `iwm_brief_bundle` with only the model stubbed: `report.conviction_inputs` holds the nine keys; `_calibrate_conviction` called with `direction=report.direction`, `confidence_score`, `analyst_agreement_count`, `ftfc_score` from the inputs and `risk_severities=['warn'] * warn_count + ['block'] * block_count` returns `report.conviction`; `rule_table_version == RULE_TABLE_VERSION`, `ladder_version == LADDER_VERSION`.
  - `test_a_null_ftfc_score_stays_null`: the same bundle with the brief row's `ftfc_score` null: `conviction_inputs.ftfc_score is None`, `ftfc_aligned is False`, and `0.0` is not among the values of `conviction_inputs.model_dump()`.
  - Review Focus `test_an_old_report_loads`: a stored report JSON without `conviction_inputs` validates with the field None.
- [ ] **Step 2: Run** (expect FAIL: the field does not exist), implement, run again (expect pass), then `python3 -m pytest tests/agents tests/api -q`.
- [ ] **Step 3: Render step, then commit** `feat(insight): store the inputs each report's conviction was computed from`.

## Task 10: The API response

Spec: Design 3 ("Stored going forward"); Risks ("Old reports lack `conviction_inputs`"). Closes V9.

**Files:** Create `tests/api/test_insight_report_conviction_inputs.py`.

- [ ] **Step 1: Write the test**, built as `tests/api/test_insight_report_conservative_short.py` is (canned bundle, the real `run_insight_pipeline` with only the model stubbed, the real `_upsert_report` into a captured connection, the real router through a fake connection), on IWM: `GET /api/insights/report/IWM` returns `conviction` and `conviction_inputs`, and `_calibrate_conviction` on the returned inputs (as Task 9) equals the returned `conviction`. A second case stores a report JSON without the field and asserts the response's `report` is that JSON unchanged. Sockets are refused as in that file.
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_insight_report_conviction_inputs.py -q` (expect pass on Task 9's code; on the branch before Task 9 it fails, recorded in the PR body), then commit `test(api): the insight report serves its conviction inputs`.

## Task 11: Close

Spec: done_when V10; Close-out; product-delivery Phase 4 and Phase 5. Closes V10.

- [ ] Run `make test` on the head; paste the summary line into the PR body.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-INSIGHT-001` record (`:279` on origin/main 3a59299ba): append this PR to its Status text (implementation under review, not deployed) and set Last reviewed to the date of the PR's head commit. `docs/product/12-PR-ISSUE-TRACEABILITY.md`, `### FEAT-INSIGHT-001` (`:495`): append the PR to its PR lineage, naming spec PR #2009. Commit: `docs(product): record the reachable conviction under FEAT-INSIGHT-001`.
- [ ] The spec declares no `site_source_notes` and no canvases, so no site note and no canvas marker are owed.
- [ ] Render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass).
- [ ] Docs audit: `python3 scripts/maintenance/docs_audit.py` on the branch and on a detached `origin/main` worktree; the branch reports no line that `main` does not.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] PR body: the Capacity section; every done_when box ticked with its evidence (test names, the two execution ids, the evidence file path); the red then green record; the owner's reply quoted under V3. Then mark the PR ready. No gate file is touched, so no red-team pass is owed.

## Close-out (not tasks; the owner's steps)

From the spec's Close-out. None runs from the implementation PR, none is a done_when box, and each needs the owner's own yes.

1. Deploy: `./gcp/deploy.sh insights`, from `main` at or after the merge.
2. Replay sessions the owner names through `INSIGHT_AS_OF` and read back the levels and their `conviction_inputs` (a model spend; its size was not read).
3. Read the distribution, read-only: levels by ticker over the replayed sessions, and every report's level recomputed from its stored inputs.
4. Browser proof for the insights report card, as AGENTS.md defines.
5. Rerun the measurement when the filled sample has doubled or the brief's rule version changes (`python -m lib.agents.rule_evidence` on fresh reads), and bring any changed verdict to the owner as a new decision.
6. On a `docs/` branch after the merge: this plan's `status: done` and `docs/product/08-AI-AGENT-ARCHITECTURE.md`.
