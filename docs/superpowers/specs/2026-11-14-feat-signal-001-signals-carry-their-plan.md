---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-REL-001, REQ-REPLAY-001, REQ-VALID-001, REQ-CAP-001, REQ-CAP-002]
issues: [815]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
done_when:
  - "tests/lib/test_signal_plan.py::TestBuild passes on the shared fixture (one session of 1-minute bars, a daily frame, a LevelParams set): lib.signal_plan.build_signal_plan returns, for a call and for a put, the entry reference and its rule, the stop price with its rule and level name, T1 to T3 each with price, rule, level name and timeframe, the leg count and risk_ref; every non-null plan price equals the price of a level the builder listed or a bar extreme named by its rule; a side with no level that passes the stop window gives stop NULL and plan_status stop_unavailable; a side with no spaced target gives T1 to T3 NULL and plan_status targets_unavailable; parameters not ok give plan_status params_unavailable; no case returns a number in place of a missing level"
  - "tests/lib/test_signal_plan.py::TestNoLookAhead passes: the plan for signal bar i built from bars[0..i] equals the plan built from the whole session, and changing every bar after i (prices and volume) leaves the plan unchanged, for 20 signal bars of the fixture; the daily frame handed to the builder holds no row dated on or after the session"
  - "tests/gcp/test_signal_plan_parity.py passes: for the same ticker, bar and direction on the shared fixture, the plan written by the history step (scripts.run_historical_signals attach), by SignalMonitor.fire_alert through _persist_signal_alert, and by scripts/replay_signal_monitor.py through its capture and persist path are equal key for key after dropping the writer name; the test fails when any one writer is given a different stop"
  - "tests/meta/test_signal_plan_single_source.py passes: by AST, the only assignments to plan_version, plan_status, plan_entry_price, plan_stop_price, plan_t1_price, plan_t2_price, plan_t3_price and plan in scripts/run_historical_signals.py, gcp/signal_monitor.py and scripts/replay_signal_monitor.py take their value from lib.signal_plan.build_signal_plan, and no other module under lib/, gcp/, scripts/ or platform/ computes a plan stop or target for a signal"
  - "tests/lib/test_signal_plan.py::TestScore passes: score_signal_plan fills at the open of the bar after the signal bar, gives plan_r as the mean over legs of sign x (exit minus fill) / abs(fill minus stop), counts the stop first on a bar that touches the stop and a target, holds a leg with no target to the stop or the last regular-hours close, gives plan_r_t1 for all legs out at T1, and gives plan_r NULL with plan_r_status stop_unavailable, targets_unavailable, invalid_stop (stop not on the losing side of the fill) or session_incomplete instead of a number; no figure includes a trading cost"
  - "tests/gcp/test_premarket_playbook_resolver.py passes with no change to the file against origin/main (git diff origin/main -- tests/gcp/test_premarket_playbook_resolver.py is empty), after resolve_plan calls the shared leg walk in lib/signal_plan.py"
  - "tests/lib/test_strat_levels.py and tests/gcp/test_level_basis.py pass with no change to either file against origin/main, so the brief's triggers, targets, stops and level_basis are unchanged by the entry-anchored call path added to lib/strat_levels.py"
  - "gcp/schema.sql adds, with ADD COLUMN IF NOT EXISTS, nullable and with no default, on historical_signals and on signal_alerts: plan_version VARCHAR(24), plan_status VARCHAR(24), plan_entry_price, plan_stop_price, plan_t1_price, plan_t2_price, plan_t3_price DOUBLE PRECISION, plan JSONB, plan_fill_price DOUBLE PRECISION, plan_r DOUBLE PRECISION, plan_r_t1 DOUBLE PRECISION, plan_r_status VARCHAR(24), plan_exit VARCHAR(32), plan_t1_hit_ts, plan_t2_hit_ts, plan_t3_hit_ts TIMESTAMPTZ, plan_score_rule VARCHAR(32); tests/gcp/test_signal_plan_schema.py asserts each name, type and nullability, and tests/integration/test_signal_plan_columns_pg.py applies gcp/schema.sql twice on Postgres without error"
  - "tests/scripts/test_run_historical_signals_plan.py::test_query_shape passes: for one ticker with N signals over K sessions (N 2,500, K 20) the attach step issues exactly 5 read queries and ceil(N / 1000) writes, and the nightly generator path issues 3 read queries for plans for the whole run however many tickers it holds"
  - "tests/scripts/test_run_historical_signals_plan.py::test_attach_plans passes: --attach-plans --start-date D updates plan and outcome columns of stored rows from D on, changes no other column and no row before D, never deletes, and a second run changes nothing; a stored row whose entry_time has no bar in the frame, or whose entry_price differs from that bar's close by more than half a cent, gets plan_status bar_mismatch and NULL plan prices; --attach-plans with --dry-run writes nothing"
  - "tests/gcp/test_signal_monitor_persist.py::TestSignalPlanPersist passes: a fire persists the plan columns from the session levels already in memory with no new query; a fire whose session levels are unavailable still persists the alert, with plan_status levels_unavailable and every plan price NULL; target_price, time_stop_minutes and the active position dict equal origin/main's for the same fire"
  - "tests/gcp/test_signal_monitor_eod_resolver.py::TestPlanOutcome passes: the resolver writes plan_fill_price, plan_r, plan_r_t1, plan_r_status, plan_exit, the three hit timestamps and plan_score_rule for an alert that carries a plan, writes plan_r_status with NULL plan_r for one that does not, and exit_ts, exit_reason, exit_price and exit_return_pct equal origin/main's for the same fixtures"
  - "tests/api/test_signal_plan_not_served.py passes: GET /api/signals/{ticker} and GET /api/signals/{ticker}/similar, over rows that hold plan columns, return exactly the keys they return on origin/main, and platform/api/openapi.json is unchanged (git diff origin/main -- platform/api/openapi.json is empty); tests/gcp/test_signal_monitor.py::TestEmbedUnchanged asserts the Discord embed description of a fixture fire is byte-equal to origin/main's"
  - "docs/product/07-MODEL-REGISTRY.md row MODEL-EXIT-001 names lib/signal_plan.py and the plan columns, python3 scripts/gate/export_model_registry.py is run and its JSON committed, the FEAT-SIGNAL-001 catalog record (Status, Last reviewed) and the PR traceability entry are updated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
  - "The PR body carries the Capacity section of this spec with the attach run's measured numbers from a --dry-run on one ticker (signals, read queries, seconds per stage), next to the estimates"
status: draft
supersedes: null
---

# Signals carry their plan: entry, stop, T1 to T3 and the rule behind each, built once, stored on the row and scored in R

## Authority and status

Draft, written 2026-11-14 for the owner's review. Nothing here is approved and no code is written under
it. The section-by-section approval conversation of the product-delivery skill is replaced, for this
draft, by the numbered list in "Decisions for the owner".

The owner's request (T, 2026-11-14), verbatim: "A signal should carry its full plan at the moment it is
created: entry, stop, T1 to T3, and the rule that produced each. That is what #1832 does for the brief
plan. The momentum signals and live alerts should get the same treatment, so that every signal can be
scored in R against its own stop". Also: "What is a signal if it doesn't have a target entry, tp targets
and stop loss", and "its good that price reaches the target".

Every statement below about code or data is marked "read" (read in the source, not executed) or "run"
(a query or command was executed; the execution name is in "Queries run"). Code references are to
origin/main at 572a6362 unless they name the #1832 branch, which is
origin/fix/feat-strat-001-brief-exits-in-thirds at 69e181f5.

## Capability

FEAT-SIGNAL-001 owns this. Its row in `docs/product/02-FEATURE-CATALOG.md` (line 21):

> | [FEAT-SIGNAL-001](#feat-signal-001) | Signals / execution | Signal discovery, alerting, exits | `/signals`, `/live` | `/api/signals` | `signal_alerts`, `historical_signals`, `exit_config_overrides` | Production but needs remediation | P0 | 1 | 25 | [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#928](https://github.com/TeneikaAskew/stocks/issues/928) [#1206](https://github.com/TeneikaAskew/stocks/issues/1206) |

Two capabilities are involved. FEAT-SIGNAL-001 owns the signals, the live alerts, both tables and the
exit model (MODEL-EXIT-001), so it owns the plan a signal carries and its score. FEAT-STRAT-001 owns the
level builder in `lib/strat_levels.py` ("the one level builder: levels, side lists, broken status,
window, triggers, stops, targets and reason per side", its catalog record) and #1832. This spec calls
that builder and adds one entry-anchored call path to it; the brief's own output is pinned unchanged by
its existing tests. That is one spec under FEAT-SIGNAL-001, the way #1832 (FEAT-STRAT-001) changed
`gcp/signal_monitor.py` as a consumer. The work is split in two by what a user can see, not by
capability: see "Size and split".

## Decisions for the owner

Answer by number. Each has a recommendation and the evidence for it.

1. **The stop rule.** Options: (a) the signal bar's opposite side, (b) a multiple of ATR, (c) the
   nearest level on the other side of the entry, which is the brief's stop today
   (`lib/strat_levels.py:2351-2352`, read).
   **Recommended: (c) as the signal's stop, with (a) and (b) also recorded on every signal.**
   - (a) gives an R that cannot be read. The exit evaluation scored its check days against the signal
     bar's opposite side and says: "R is in `final_tables/check_days.csv` but is not usable on these
     days: the stop is one 1-minute bar wide, so results read as tens or hundreds of R"
     (`signal-eval/report.md`, section 5 and section 7, "Noise").
   - (b) has no calibrated multiple for a 1-minute signal. The per-ticker `stop_*_atr` keys were
     calibrated for the planner's entry zones on daily ATR (`persona_stop_price`,
     `lib/strat_levels.py:992-1017`, read). Whether they suit a momentum signal is not checked.
   - (c) is a named level, is the same kind of R the brief's plan is scored in, and is what "the same
     treatment" as #1832 means. Its cost: when no level passes the stop window the signal has no stop
     (pinned for the brief by `tests/lib/test_strat_levels_playbook.py::test_no_stop_when_no_fresh_opposite`),
     and a level stop can sit far from a signal fired mid-range. How often either happens for signals
     is not checked: no run has built level stops for signals.
   - Recording all three costs two numbers per row and lets the first clean run report, per rule, the
     share of signals with a stop and the size of 1 R in percent of price, so the choice can be changed
     with a version bump and no second pass over history.
2. **The target rule.** Options: next levels as in #1832, ATR multiples, or both with one primary.
   **Recommended: next levels only, spaced by the ticker's `target_min_spacing_atr` as #1832 does.**
   Each target then has a level and a rule behind it, which is what was asked. ATR targets are not
   stored: in table D no ATR target exit passes the gate on any ticker, with a fixed or a trailing ATR
   stop (best fixed-stop exit, % per session, before and after 2026-05-01: SPY +0.051 and -0.002, QQQ
   +0.124 and +0.055, IWM +0.107 and -0.108), and the best multiple differs by ticker, so there is no
   multiple to store. An ATR target can still be evaluated later from the bars without a stored one.
3. **The exit plan to score.** Options: thirds at T1 to T3, all out at T1, T1 then a trail.
   **Recommended: score thirds as `plan_r` (the #1832 shape) and all out at T1 beside it as
   `plan_r_t1`; no trail.** The evidence points two ways, so both are stored:
   - Levels are reached far more often than they hold: before May 2026, pooled over the three tickers,
     "T1 is reached on 54% to 66% of triggers but price holds five 1-minute closes beyond it on 10% to
     16%. T2 is reached on 25% to 38% and held on 4% to 9%; T3 on 12% to 21% and held on 3% to 4%"
     (`signal-eval/report.md`, "What to take from it" point 5; section 4 gives 44% to 67% reached and
     0% to 15% held after May). Those are level triggers, not momentum signals. With T2 reached on at
     most 38% and T3 on at most 21%, the second and third legs mostly do not exit at their targets,
     which is the case for taking everything at T1.
   - The #1832 spec's research found the opposite on the brief's own triggers, 2016-03-01 to
     2025-02-28: all out at T1 made -88.7 R and thirds were +136.4 R better (its Problem section; the
     research files are not in the repo, the bars were the old adjusted ones, not re-run here).
   - On regenerated momentum signals neither wins: "level targets in thirds" is SPY -0.008 before and
     -0.001 after, QQQ +0.039 and +0.002, IWM +0.008 and -0.061; "first level target, then ATR trail"
     is SPY -0.009 and -0.008, QQQ +0.018 and +0.002, IWM +0.039 and -0.078; no row passes the gate
     (table D, all sessions, % per session, 293 sessions before and 137 after). A trail adds a
     parameter and shows nothing, so it is not stored.
4. **A signal with no valid stop or no target.** **Recommended: store it, never drop it and never fill
   the gap.** The missing price is NULL, `plan_status` names the first missing piece
   (`stop_unavailable`, `targets_unavailable`, `params_unavailable`, `levels_unavailable`,
   `atr_unavailable`, `outside_session`, `bar_mismatch`), and `plan_r` is NULL with a
   `plan_r_status`. Rule 3.7: a level that does not exist is never replaced by a computed one. The live monitor already persists every
   fire whatever the Discord gate decides (`gcp/signal_monitor.py:1653-1674`, read).
5. **What live alerts post to Discord.** **Recommended: no change in this spec; the row carries the plan
   from the first fire, and the embed changes in the second spec.** The monitor still exits on its
   percent target, time stop and RSI (`gcp/signal_monitor.py:2150-2162`, read) and has no stop per
   trade by a recorded decision (`lib/config.py:309-338`, read; issue #815). An embed that shows a
   stop and T1 to T3 would describe a trade the monitor does not manage, and thirds at level targets
   show no edge in table D. If the owner wants it now: two lines, "Recorded plan (not the monitor's
   exit): stop X (level), T1 to T3", which moves one task and its test into this spec.
6. **History.** Options: regenerate all stored signals with plans, plans only from a date, or forward
   only. **Recommended: attach plans to the stored signals of SPY, QQQ and IWM from 2025-03-03 by
   update, with no delete and no regeneration; live alerts get plans from the deploy on and are not
   backfilled.**
   - A plan is a function of the signal's bar, its direction and the session's levels. The signals
     themselves do not change, so nothing needs regenerating a second time once the runbook's
     regeneration of `historical_signals` on the clean bars has run. Before that it must not run: most
     stored signals of 2026-04 to 2026-09 carry Eastern-label times, and in 09:30 to 15:34 only 5% to
     35% of them coincide with a regenerated signal (`clean-set/STATUS.md`, 18:49Z). As a guard, a
     stored row whose entry_time has no bar, or whose entry_price is not that bar's close, gets
     `plan_status` `bar_mismatch` and no plan.
   - The only regeneration path that exists is `--force`, which deletes every row of the ticker and
     strategy before it generates and commits that delete first (`gcp/historical_signals.py:118-137`
     and `scripts/run_historical_signals.py:453-460`, read; hazards 1 and 2 of the recompute spec). An
     update in chunks cannot leave a ticker empty.
   - 2025-03-03 is the window already measured: 293 sessions before 2026-05-01 and 137 after, 43,573,
     44,000 and 39,025 momentum signals (`clean-set/STATUS.md`, 18:45Z).
   - **A plan needs the ticker's level parameters in force on the session, and production has none
     before 2026-11-12** (run, db-query-8ptk7: `ticker_level_params` holds 23 `on_demand` rows per
     ticker, all effective 2026-11-12; SPY has 19 of 23 ok). Until the history-mode calibration of
     FEAT-STRAT-001 is written for the window, every stored signal before 2026-11-12 would get
     `params_unavailable`. So this decision is also: how far back that calibration is written. The
     local evaluation used its own local calibration.
   - Stored live alerts (3,146 live rows, run, db-query-t4nsl) keep NULL plans. A replay with
     `REPLAY_DATE` writes `run_kind='replay'` rows with plans for any date whose parameters exist.
7. **Where the split falls.** **Recommended: two specs.** This one builds, stores and scores the plan
   and changes nothing a user sees. The second shows it: Discord embed, `/api/signals` fields, the
   OpenAPI snapshot, solyra types, fixtures and Playwright evidence. See "Size and split".

## Problem

A stored signal is a time, a direction and a price. It has no stop and, in history, no target, so it
cannot be scored in R, and every evaluation so far had to invent the plan afterwards.

What is true today:

- **`historical_signals`** holds ticker, entry_time, trade_type, entry_price, signal_strength,
  indicators at entry and best-case returns at fixed windows of 5 to 60 minutes
  (`gcp/schema.sql:2339-2372`, read), plus `realized_return_pct` under one fixed 20-minute exit
  (`:2392-2394`, read). No stop and no target: the three signal tables hold no column named like stop,
  plan, t1 or target except `signal_alerts.target_price` and `time_stop_minutes` (run, db-query-t4nsl).
  One correction to the request's wording: the schema comment says signal_strength is 3 to 5, but the
  generator on main needs 5 or more of 7 conditions (`lib/trading_analysis.py:995`, `:1069`, read) and
  the rows stored since 2026-10-01 hold 5, 6 and 7 only (run, db-query-8rb9b).
- **`signal_alerts`** holds direction, scores, price_at_signal, one `target_price`, `time_stop_minutes`
  and the exit columns (`gcp/schema.sql:1085-1118`, `:3870-3875`, read). The target is the signal price
  moved by a per-ticker percent, and the time stop is in minutes (`gcp/signal_monitor.py:1548-1554`,
  read). There is no stop price. Exits are target, time stop, RSI or a fixed horizon in the monitor
  (`:2117-2167`, read) and the same rules in the end-of-day resolver, which closes what is left at the
  last bar (`gcp/signal_monitor_eod_resolver.py:241-286`, `:342-378`, read). Of 3,146 live alerts, 2,674
  ended on the time stop, 445 on the target, 20 on RSI and 7 at the close (run, db-query-8rb9b).
- **The replay does not go through `fire_alert`.** It swaps in a capture function and has its own
  insert that writes no `target_price` and no price (`scripts/replay_signal_monitor.py:536-600`,
  `:601-667`, read); the 23 stored replay rows have no target (run, db-query-t4nsl). A plan added to
  `fire_alert` alone would not reach the replay.
- **The evaluation attached plans afterwards.** Its legs "enter at the open of the bar after their
  signal bar and stop at the signal bar's opposite side", with targets from ATR or the next levels
  (`signal-eval/report.md`, section 5). Those rules live in evaluation code, not in the product.
- **What that evaluation found**, on clean bars with regenerated momentum signals, 2025-03-03 to
  2026-11-13, SPY, QQQ and IWM, % per session (table D,
  `clean-set/D_momentum_exit_kinds_t2_regenerated.csv`, all sessions): level targets in thirds show no
  edge on any ticker (numbers in decision 3). Hold to the close on QQQ is +0.184 before 2026-05-01
  (t 2.66) and +0.225 after (t 2.74) and passes the gate (5th percentile +0.111). One more row reads
  `gate_passes` True in that file: SPY under today's 20-minute rule, +0.069 before (t 1.95) and +0.063
  after (t 1.55), 5th percentile +0.006. The request named the QQQ row as the only one; the file has
  both.

Full paths of the evidence files, all under
`/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/`:
`clean-set/D_momentum_exit_kinds_t2_regenerated.csv`, `clean-set/STATUS.md`, `signal-eval/report.md`.
They are session files, not in the repo.

## Non-goals (what does not change)

- Which bars fire a signal, its score, its gates and its size. The history generator and the live
  monitor stay two generators; this spec makes their plans equal for the same bar, not their signals.
- How the monitor exits: `target_price`, `time_stop_minutes`, the RSI exit, the fixed horizon,
  `exit_config_overrides`, and the `exit_*` columns the monitor and the resolver write. No live stop
  is added. Issue #815 stays open; this spec gives it data, not a decision.
- The Discord embed and every API response (decision 5), `realized_return_pct`, the return windows,
  and `signal_metrics`.
- The brief's plan, `level_basis` and the brief resolver's outputs.
- The brief's 10:00 ET entry cutoff is not applied to signals. A signal after it still gets a plan;
  its bar time is on the row.
- No new kind of level. Targets and stops come from the levels the builder already lists; ORB levels
  are not added.
- No change to `scripts/run_historical_signals.py --force`.

## Approaches considered

1. **Reuse #1832's builder as is.** Not possible. `_pick_side` takes the first unbroken rung past the
   reference as the trigger and plans targets from that rung (`lib/strat_levels.py:2356-2443` on the
   #1832 branch, `_plan_targets` at `:2445`, read). A signal enters at the market on the next bar, so
   its T1 would be skipped. `_plan_targets` also publishes no target unless `entry_cutoff_et` is ok,
   and a signal has no cutoff.
2. **A separate plan builder for signals.** Rejected: two sets of level rules, the drift the one level
   source spec removed.
3. **One entry-anchored call path into the same builder, one function for the three writers
   (chosen).** The side rule, broken rule, window, spacing and stop stay in `lib/strat_levels.py`.
4. **Score in `signal_metrics`.** Rejected: its rows are keyed to signals a regeneration may drop
   (hazard 3 of the recompute spec), it stores fractions, and a second job would rebuild the bar walk.
   The outcome goes on the signal's own row, as `realized_return_pct` does.

## Design

### 1. What a plan is

One record per signal, built from bars at or before the signal bar:

| Part | Value | Rule recorded |
|---|---|---|
| Entry | reference price: the signal bar's close. The fill is the next bar's open and is known only at scoring | `next-open-v1` |
| Stop | the nearest level on the other side of the reference that passes the stop window (decision 1), with its level name and timeframe; the bar-opposite and ATR stops as alternates | `level-other-side-v1`, `bar-opposite-v1`, `atr-multiple-v1` |
| T1 to T3 | the next levels past the cleared mark in the signal's direction, each at least `target_min_spacing_atr` x ATR past the entry or the target before it, up to `exit_legs` of them, each with level name and timeframe | `next-level-spaced-v1` |
| Legs | `exit_legs` from the policy (3), each 1/legs of the position | policy row |
| R unit | `risk_ref` = abs(reference minus stop) at creation; R at scoring is abs(fill minus stop) | stated in the record |

The cleared mark is the further of two prices: the builder's own mark for the session (its reference
and the accepted premarket extreme) and the regular-session high (for a call) or low (for a put) through
the signal bar. A level between the entry reference and that mark has already traded and is never a
target: the builder's existing broken rule, extended by the session's own bars. Both inputs exist in
every writer (the monitor keeps regular-session extremes, `gcp/signal_monitor.py:422-466`, read).

The record also holds the bar time, session date, the level source (`level_basis` or built), the level
rule version, the ATR basis and value, the reference and cleared marks, each parameter used with its
status, method and effective date, and the builder's version (REQ-DATA-003).

### 2. Where it is computed

`lib/signal_plan.py` (new), two functions and nothing else:

- `build_signal_plan(direction, bars_to_signal, session_levels) -> SignalPlan`. The only place a
  signal's stop or target is computed. It calls a new public entry-anchored function in
  `lib/strat_levels.py` that runs the existing side pick with the entry as the anchor rung and no
  cutoff requirement. A new file because neither `lib/signals.py` (conditions and scores) nor
  `lib/strat_levels.py` (session levels) is the home of bar-anchored entries and leg scoring; the plan
  may fold it into `lib/strat_levels.py` if review prefers.
- `score_signal_plan(plan, bars_after_signal) -> PlanOutcome`. The leg walk now inside `resolve_plan`
  (`gcp/premarket_playbook_resolver.py:473-585` on the #1832 branch, read) moves here and
  `resolve_plan` calls it, so the brief and the signals are scored by one walk. One stated difference:
  a signal fills at the entry bar's open, so that bar counts for targets as well as for the stop; the
  brief's call keeps its own value of that argument.

The three writers call `build_signal_plan` and nothing else:

- **History.** `scripts/run_historical_signals.py::_process_ticker`, after the signals frame exists
  and before `map_signals_to_table`, for both strategies. `lib/trading_analysis.py` is not changed.
  The same step serves `--attach-plans` (decision 6).
- **Live.** A method `SignalMonitor._signal_plan(ticker, sig, latest)` reads
  `self.session_levels[ticker]` and `self.session_extremes[ticker]`, both already in memory
  (`gcp/signal_monitor.py:987`, `:422-466`, read), is called in `fire_alert`, and its result is passed
  to `_persist_signal_alert`.
- **Replay.** The capture function calls the same `_signal_plan`, `FireRecord` carries the plan, and
  the replay's insert writes the plan columns.

History resolves a session's levels in the monitor's order: the stored live `level_basis` for the
session when there is one, else `build_session_levels` on the daily frame before the session, the
session's premarket snapshot and the parameters in force (`gcp/signal_monitor.py:976-982`, read).

### 3. Where it is stored

Additive, nullable, no default (a metadata-only ALTER), the same names on `historical_signals` and
`signal_alerts`:

| Column | Type | Meaning |
|---|---|---|
| `plan_version` | VARCHAR(24) | `signal-plan.v1`; NULL on a row written before plans existed |
| `plan_status` | VARCHAR(24) | `ok`, or the first missing piece (decision 4) |
| `plan_entry_price` | DOUBLE PRECISION | the reference: the signal bar's close |
| `plan_stop_price` | DOUBLE PRECISION | the stop, NULL when there is none |
| `plan_t1_price`, `plan_t2_price`, `plan_t3_price` | DOUBLE PRECISION | the targets, NULL when there is none |
| `plan` | JSONB | the whole record of Design 1, with the rule and level behind each price |

`signal_alerts.target_price` keeps its meaning (the monitor's percent target). It is not T1.

### 4. How a signal is scored in R against its own stop

On the signal's own row, written by the generator at insert and by `--attach-plans` for
`historical_signals`, and by the end-of-day resolver for `signal_alerts`:

| Column | Type | Meaning |
|---|---|---|
| `plan_fill_price` | DOUBLE PRECISION | the open of the bar after the signal bar, same session |
| `plan_r` | DOUBLE PRECISION | mean over legs of sign x (exit minus fill) / abs(fill minus stop), gross, no costs; NULL unless `plan_r_status` is `ok` |
| `plan_r_t1` | DOUBLE PRECISION | the same with every leg out at T1 (decision 3) |
| `plan_r_status` | VARCHAR(24) | `ok`, `stop_unavailable`, `targets_unavailable`, `invalid_stop`, `session_incomplete`, `outside_session` |
| `plan_exit` | VARCHAR(32) | the legs' exits in order, for example `t1,t2,close` |
| `plan_t1_hit_ts` to `plan_t3_hit_ts` | TIMESTAMPTZ | first bar at or after the fill that reaches each target, whatever the legs did |
| `plan_score_rule` | VARCHAR(32) | `signal-legs-v1` |

Within the walk a target fills at its price, the stop at its price or at a later bar's open beyond it,
a bar touching both counts the stop first, and legs still open exit at the last regular-hours close:
#1832's rules. A session whose final regular-hours bars are not in the frame is `session_incomplete`,
never a number. History rows are written once (`ON CONFLICT DO NOTHING`), so the nightly run, which
starts at 01:00 ET after the session, scores complete sessions; `--attach-plans` is the path that
rewrites plan and outcome columns.

### 5. Reads and writes (Rule 0)

- Monitor, per fire: no new query. One `build_signal_plan` call on state already in memory.
- Resolver, per alert: no new query. The day's bars are already loaded once per ticker and day; the
  existing UPDATE gains the outcome columns.
- Nightly generator, per run: three more reads for the whole run (level parameters for the session,
  live `level_basis` rows, and daily rows with their premarket fields, each for all tickers in one
  query), none per signal or per ticker.
- `--attach-plans`, per ticker: five reads (bars for the window, the stored signals' keys, daily rows
  with their premarket fields, parameters in force over the range, `level_basis` rows over the range)
  and one multi-row UPDATE per 1,000 signals, committed per chunk, with a progress line per chunk.
  The range read of parameters is a new one-query function beside `load_level_params`
  (`lib/strat_levels.py:1256`, read), which reads one session per call.

## Order against work in progress

Two conditions come first:

1. **Clean bars.** No stored signal is given a plan or scored before the month replace and rebuilds
   planned for 2026-11-14 and 11-15 are done and verified, and `historical_signals` has been
   regenerated on those bars by the runbook (REQ-VALID-001). Code and tests may land before; the
   attach run and any scored figure may not.
2. **#1832 on main.** This spec reuses its spacing, legs, `gate_targets` split and leg walk. Its
   implementation branch is cut only from a main that holds #1832 (open, not a draft, head 69e181f5,
   read from GitHub on 2026-11-14).

Files this spec would touch: `lib/signal_plan.py` (new), `lib/strat_levels.py`,
`gcp/premarket_playbook_resolver.py`, `gcp/schema.sql`, `gcp/historical_signals.py`,
`scripts/run_historical_signals.py`, `gcp/signal_monitor.py`, `scripts/replay_signal_monitor.py`,
`gcp/signal_monitor_eod_resolver.py`, their tests, `docs/product/07-MODEL-REGISTRY.md` (one row) and
the FEAT-SIGNAL-001 catalog and traceability entries.

| Open work | Files it changes outside docs and tests | Overlap with this spec | Order that avoids a conflict |
|---|---|---|---|
| `fix/feat-data-001-deployed-dates-exchange-clock`, PR #1948 (10fd2c2b) | 39 files, among them `gcp/signal_monitor.py` (lines 36 and 381), `lib/trading_analysis.py:618`, `lib/strategies/exit_config_overrides.py`, `gcp/trade_logger.py` | `gcp/signal_monitor.py`, different hunks (this spec changes `fire_alert` and `_persist_signal_alert`, lines 1448 to 1870). Nothing else: this spec does not change `lib/trading_analysis.py` | #1948 merges first; this branch is cut after |
| `feature/feat-data-001-recompute-after-bar-rewrite` (local branch, e2ba7f7b, 15 commits, not on origin) | `gcp/bar_recompute.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/gcs_utils.py`, `gcp/schema.sql`, `gcp/signal_monitor_eod_resolver.py` | **Two files.** `gcp/schema.sql`: both append at the end of the file. `gcp/signal_monitor_eod_resolver.py`: it rewrites the walk this spec adds the plan outcome to | The recompute merges first. This spec's resolver task is written against its walk (which ends at the session close) |
| `feature/feat-playbook-001-brief-late-slot` (no commits yet) | by its spec, only `gcp/premarket_brief.py` and `gcp/fetchers/fetch_premarket_refresh.py` | none in files. In data: it rewrites the day's `level_basis` at 09:20, which the monitor reads; the plan records the level source it used | none needed |
| The replace-tool fix | `gcp/fetchers/fetch_alphavantage_intraday.py` | none | none needed |
| PR #1832 (69e181f5) | `lib/strat_levels.py`, `gcp/premarket_playbook_resolver.py`, `gcp/schema.sql`, `gcp/signal_monitor.py`, `gcp/premarket_brief.py`, `lib/level_calibration.py`, `lib/agents/summarizers.py` | four files, by design | #1832 merges first (condition 2) |
| PR #1823, FEAT-SIGNAL-001 gate decision record (not in the list given, found while checking) | `gcp/signal_monitor.py` (lines 1400 to 1460, 1694, 1800) | the same function, `_persist_signal_alert` | #1823 merges first, or this branch rebases on it before review |

So the answer to "none of them is touched" is no for two of the four named: #1948 shares one file in
different hunks, and the recompute branch shares two files. Cutting this branch after both are on main
avoids every conflict.

## Size and split

About 23 tasks in all, so two specs.

- **This spec, about 15 tasks: carry and score.** The entry-anchored call path; `build_signal_plan`;
  the look-ahead tests; `score_signal_plan` and the brief resolver on it; the range parameter read;
  the columns; the generator step; `--attach-plans`; the monitor; the replay; the parity and
  single-source tests; the resolver outcome; the unchanged-surface tests; the registry row and product
  records; the dry-run measurement.
- **Second spec, about 8 tasks: show.** The Discord embed, plan and R fields on
  `/api/signals/{ticker}` and `/similar` with an API test of the changed response and the regenerated
  OpenAPI snapshot, solyra's types, fixtures, hermetic Playwright evidence and the cloud spec, and R in
  the weekly quality report. It starts after the first scored month exists, so what is shown has been
  measured.

The line: nothing a user can see changes in this spec, and `tests/api/test_signal_plan_not_served.py`
holds that at the API. If decision 5 is answered "now", the embed task and its test move here.

## Capacity and cost

Estimates are marked; nothing below was measured for this design except where a file is named.

**Attach run, 2025-03-03 to 2026-11-13, per ticker** (decision 6):

- Volume: about 44,000 signals (measured count of the local regeneration: 43,573, 44,000 and 39,025;
  `clean-set/STATUS.md`). Bars: about 430 sessions x 960 minutes, about 413,000 rows (estimate). Plan
  JSON about 0.5 KB a row (estimate), so about 22 MB a ticker and about 63 MB for the three, on a table
  of about 3.4 GB (`gcp/deploy.sh:4894-4896`, read).
- Velocity: 5 reads and 44 UPDATE round trips per ticker; no query per signal or per session.
- Wall-clock: reads 5 x 0.5 to 2 s (the bar read is larger; not measured); plans and scores in memory,
  not measured, budget 120 s; writes 44 x 0.5 to 2 s = 22 to 88 s. About 3 to 5 minutes a ticker
  (estimate) against the job's 1,800 s task timeout, more than 4 times headroom. No indicators are
  recomputed, so the 555 to 596 s per ticker the local regeneration took (same file) is not paid.
- Run as an execution of the existing `historical-signals-watchlist` job with `--args`, one ticker
  per execution; a retry or a rerun converges because the update is keyed and idempotent.
- Cost: under 0.01 USD a ticker at about 5 minutes of 1 vCPU and 2 GiB (estimate).

**Regenerating history is not part of this design.** If the owner chooses it in decision 6 instead:
the measured local rate is about 44,000 signals in about 590 s per ticker for 430 sessions; the full
stored history is 2,984 sessions a ticker (`clean-set/STATUS.md`, 18:39Z), about 7 times that, so about
68 minutes a ticker for generation alone (estimate, local speed), over the 1,800 s task timeout, and
it deletes 1,557,534 stored rows of the three tickers first (run, db-query-t4nsl).

**Nightly generator:** up to 25 tickers; 3 more reads a run; a few hundred plans; seconds (estimate).
No new scheduled job, so no new monthly cost line. **Monitor:** about 23 fires a day (3,146 live
alerts over the 137 sessions from 2026-05-01 to 2026-11-13, run), one in-memory call each.
**Resolver:** the same alerts, no new read.

## Close-out

After the merge, recorded on the PR, each with its execution name:

1. The owner's yes for the column apply, then `gcp/apply_schema.py`; a query of
   `information_schema.columns` shows the 17 columns on each table.
2. Deploy. The next live fire's row: `SELECT plan_version, plan_status, plan_stop_price,
   plan_t1_price FROM signal_alerts WHERE alert_date = <day> AND run_kind = 'live'`. The next resolver
   run fills `plan_r_status` on every such row.
3. Replay of that day through the production path (`REPLAY_DATE`). Its fire records carry the plan;
   they are compared with that day's live rows by ticker and the plan's bar time. Expected: no
   difference; any difference is listed with the inputs each side recorded.
4. The next nightly generator run writes plans on its new `historical_signals` rows.
5. After the clean bars are verified and the level parameters cover the window: `--attach-plans
   --dry-run` on one ticker (numbers into the PR), then the committed runs, then per ticker and per
   stop rule the share of signals with a stop, the size of 1 R in percent of price, and mean `plan_r`
   and `plan_r_t1` before and after 2026-05-01. No figure with costs.
6. Canvas refresh pending for the models diagram, run from chat after the merge.

## Risks

- **History and live get different inputs for the same bar.** The function is shared; the session's
  levels and the cleared mark are read from different places (stored basis and the monitor's bars, or
  the full bar frame). The plan records its reference, cleared marks and level source, the parity test
  pins the function, and close-out step 3 measures the inputs on a real day.
- **Most early signals may have no stop.** Decision 1's cost. The alternates on every row and
  close-out step 5 measure it before anyone relies on `plan_r`.
- **Look-ahead through the levels.** A daily row for the session itself, or a `level_basis` rewritten
  later in the day, would leak. The look-ahead test bounds the daily frame; the record keeps the basis
  it read.
- **History's premarket fields.** The stored premarket high and low of past sessions were computed from
  the old bars and are used only when filtered with the ticker's thresholds; otherwise the builder
  records the premarket as unavailable or unfiltered and builds without it. The plan keeps that status,
  so such sessions can be counted. Their recompute is the recompute spec's, not this one's.
- **The brief's scoring moves when its walk is extracted.** Held by its test file passing unchanged.
- **A plan reads as advice.** Nothing shows it until the second spec, and thirds at level targets have
  shown no edge so far.

## What was not verified

- How often a signal has a level stop, a spaced T1, or all three targets: not checked. No run has
  built plans for signals with the production builder.
- The speed of `build_signal_plan` and `score_signal_plan`, the bar read for the window, and Cloud Run
  speed against the local machine: not checked.
- That history-mode calibration is point in time and how long it takes for the window: not checked.
- The replace-tool fix's own diff: not checked; only the file named in the request.
- Whether #1832's research figures hold on as-traded bars: not checked (the evaluation says the same).
- The bars' agreement with the vendor: not checked here; this spec waits for that verification.

## Queries run

Read-only, no `--commit`, 2026-11-14:

- `db-query-t4nsl`: row counts of `historical_signals` and `signal_alerts` by ticker and run kind;
  columns named like stop, plan, t1 or target on the three signal tables.
- `db-query-8ptk7`: `ticker_level_params` coverage for SPY, QQQ and IWM; `level_basis` coverage of
  `premarket_analysis`; `signal_metrics` counts; `level_param_policy` keys (25, none of #1832's yet).
- `db-query-8rb9b`: stored signal strengths since 2026-10-01; live exit reasons.
