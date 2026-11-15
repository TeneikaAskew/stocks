---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-REL-001, REQ-REPLAY-001, REQ-VALID-001, REQ-CAP-001, REQ-CAP-002]
issues: [815]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
site_source_notes: [DASHBOARD-05, JOURNAL-06]
done_when:
  - "tests/lib/test_signal_plan.py::TestBuild passes on the shared fixture (one session of 1-minute bars, a daily frame, a LevelParams set): lib.signal_plan.build_signal_plan returns, for a call and for a put, the entry reference and its rule, the stop price with its rule and level name, T1 to T3 each with price, rule, level name and timeframe, the leg count and risk_ref; every non-null plan price equals the price of a level the builder listed or a bar extreme named by its rule; a side with no level that passes the stop window gives stop NULL and plan_status stop_unavailable; a side with no spaced target gives T1 to T3 NULL and plan_status targets_unavailable; parameters not ok give plan_status params_unavailable; no case returns a number in place of a missing level"
  - "tests/lib/test_signal_plan.py::TestNoLookAhead passes: the plan for signal bar i built from bars[0..i] equals the plan built from the whole session, and changing every bar after i (prices and volume) leaves the plan unchanged, for 20 signal bars of the fixture; the daily frame handed to the builder holds no row dated on or after the session"
  - "tests/gcp/test_signal_plan_parity.py passes: for the same ticker, bar and direction on the shared fixture, the plan written by the history step (scripts.run_historical_signals::_process_ticker), by SignalMonitor.fire_alert through _persist_signal_alert, and by scripts/replay_signal_monitor.py through its capture and persist path are equal key for key after dropping the writer name; the test fails when any one writer is given a different stop; ::test_late_start_gives_no_plan feeds the monitor only the last 100 bars of a session whose earlier high is above a level (what fetch_latest_bar returns after a restart) and asserts plan_status extremes_incomplete with every plan price NULL, while the history step and a full replay of the same bar give a plan in which that level is not a target; ::test_gap_in_feed asserts the same status after a batch that does not reach back to the last bar already folded; both fail if the monitor returns a target"
  - "tests/meta/test_signal_plan_single_source.py passes: by AST, the only assignments to plan_version, plan_status, plan_entry_price, plan_stop_price, plan_t1_price, plan_t2_price, plan_t3_price and plan in scripts/run_historical_signals.py, gcp/signal_monitor.py and scripts/replay_signal_monitor.py take their value from lib.signal_plan.build_signal_plan, and no other module under lib/, gcp/, scripts/ or platform/ computes a plan stop or target for a signal"
  - "tests/lib/test_signal_plan.py::TestScore passes: score_signal_plan fills at the open of the next regular-hours bar after the signal bar, gives plan_r as the mean over legs of sign x (exit minus fill) / abs(fill minus stop), counts the stop first on a bar that touches the stop and a target, holds a leg with no target to the stop or the last regular-hours close, gives plan_r_t1 for all legs out at T1, and gives plan_r NULL with plan_r_status stop_unavailable, targets_unavailable or invalid_stop (stop not on the losing side of the fill) instead of a number, and returns no outcome at all for a session whose final regular-hours bars are not in the frame, so that row stays pending; a signal on the session's last regular-hours bar, the 15:59 ET bar of a full session (2026-11-13) and the 12:59 ET bar of a shortened one (2026-11-27), gives plan_r_status no_fill with plan_fill_price, plan_r, plan_r_t1, plan_exit and the three hit timestamps NULL, which is an outcome and not a pending row, also when the frame holds extended-hours bars after it, while a 12:59 ET signal on the full session fills at the 13:00 open; no figure includes a trading cost"
  - "tests/gcp/test_premarket_playbook_resolver.py passes with no change to the file against origin/main (git diff origin/main -- tests/gcp/test_premarket_playbook_resolver.py is empty), after resolve_plan calls the shared leg walk in lib/signal_plan.py"
  - "tests/lib/test_strat_levels.py and tests/gcp/test_level_basis.py pass with no change to either file against origin/main, so the brief's triggers, targets, stops and level_basis are unchanged by the entry-anchored call path added to lib/strat_levels.py"
  - "gcp/schema.sql adds, with ADD COLUMN IF NOT EXISTS, nullable and with no default, on historical_signals and on signal_alerts: plan_version VARCHAR(24), plan_status VARCHAR(24), plan_entry_price, plan_stop_price, plan_t1_price, plan_t2_price, plan_t3_price DOUBLE PRECISION, plan JSONB, plan_fill_price DOUBLE PRECISION, plan_r DOUBLE PRECISION, plan_r_t1 DOUBLE PRECISION, plan_r_status VARCHAR(24), plan_exit VARCHAR(32), plan_t1_hit_ts, plan_t2_hit_ts, plan_t3_hit_ts TIMESTAMPTZ, plan_score_rule VARCHAR(32), and CREATE INDEX IF NOT EXISTS idx_signal_alerts_plan_pending ON signal_alerts (alert_date) WHERE plan_version IS NOT NULL AND plan_r_status IS NULL; tests/gcp/test_signal_plan_schema.py asserts each name, type and nullability and the index predicate, and tests/integration/test_signal_plan_columns_pg.py applies gcp/schema.sql twice on Postgres without error"
  - "tests/scripts/test_run_historical_signals_plan.py::test_query_shape passes: the nightly generator path issues 4 read queries for plans and their outcomes for the whole run however many tickers it holds"
  - "tests/scripts/test_run_historical_signals_plan.py::test_pending_rows_are_scored passes: the generator inserts a row whose session is not complete in the frame with its plan and plan_r_status NULL; a later run scores every row of its tickers that has plan_version set and plan_r_status NULL inside the heal window, whether or not that run inserted it, and changes no other column; a row on its session's last regular-hours bar gets plan_r_status no_fill with plan_fill_price and plan_r NULL, is not selected by the next run and does not make the run exit nonzero; a row still pending for a session before the last complete one makes the run exit nonzero"
  - "tests/gcp/test_signal_monitor_persist.py::TestSignalPlanPersist passes: a fire persists the plan columns built from the session's open basis, which the monitor reads at most once per ticker and session (the second and later fires of the session issue no query); a fire whose session levels are unavailable still persists the alert, with plan_status levels_unavailable and every plan price NULL; target_price, time_stop_minutes and the active position dict equal origin/main's for the same fire"
  - "tests/gcp/test_signal_monitor_eod_resolver.py::TestPlanOutcome passes: the resolver writes plan_fill_price, plan_r, plan_r_t1, plan_r_status, plan_exit, the three hit timestamps and plan_score_rule for an alert that carries a plan, writes plan_r_status with NULL plan_r for one that does not, and exit_ts, exit_reason, exit_price and exit_return_pct equal origin/main's for the same fixtures"
  - "tests/gcp/test_signal_monitor_eod_resolver.py::TestPlanOutcomeRun passes, driving EODResolver.run() and main() as the scheduled job does, against one fake table that holds (a) an alert the monitor already closed (is_open false, exit_ts set, plan present, plan_r_status NULL) on a prior session whose bars are stored, (b) an open alert of that session, (c) an alert with plan_version NULL, (d) a closed alert of today whose bars are not stored yet and (e) an alert with a plan on the last regular-hours bar (15:59 ET) of that prior session: (a) and (b) get their plan outcome although find_open_alerts returns only (b); (e) gets plan_r_status no_fill with plan_fill_price and plan_r NULL and is not selected by a second run; the exit_ts, exit_reason, exit_price, exit_return_pct and is_open of (a) and its trades row are unchanged; (c) is never selected; (d) stays pending and the run exits 0, which it would not if (e) were left pending; the same run with (a)'s bars missing exits nonzero; a run in which find_open_alerts returns no row still scores (a); the selection issues one query whose text holds no is_open and no exit_ts predicate; the suite fails when the pending selection is replaced by find_open_alerts"
  - "tests/api/test_signal_plan_not_served.py passes: GET /api/signals/{ticker} and GET /api/signals/{ticker}/similar, over rows that hold plan columns, return exactly the keys they return on origin/main, and platform/api/openapi.json is unchanged (git diff origin/main -- platform/api/openapi.json is empty); tests/gcp/test_signal_monitor.py::TestEmbedUnchanged asserts the Discord embed description of a fixture fire is byte-equal to origin/main's"
  - "tests/gcp/test_signal_plan_level_source.py::test_plan_levels_come_from_the_brief_basis passes: for one fixture session with a stored live level_basis, the plan written by each of the three writers takes the level name and price of its stop, of T1 to T3 and of brief_trigger from SessionLevels.from_basis of that stored basis; plan.levels.source is level_basis and holds the basis rule_version and built_at; a level added to the daily frame that the stored basis does not hold never appears in the plan; brief_trigger holds the name and price of the brief's trigger for the signal's side and its role, one of stop, t1, t2, t3 or none, matched by name and cent, or not_published when the brief gave that side no trigger; for a session with no stored basis the source is built and brief_trigger is NULL"
  - "tests/gcp/test_signal_plan_level_source.py::TestOpenBasis passes for lib.strat_levels.read_open_level_basis and for each of the three writers: with an early write at 08:30 and a late write at 09:22, a signal at 09:35 and one at 14:00 both get the 09:22 basis; when the canonical live row is overwritten at 10:32, after the 09:35 signal was planned, the history step and a monitor started at 11:00 give that session's signals plan_status basis_replaced with every plan price NULL, never the 10:32 levels and never a rebuild; a history row written before the open by a run that did not reach the canonical row (a second scheduled run) is never selected; a session whose live row was replaced by a replay row is basis_replaced; a session with no stored live basis at all is built by the builder; the reader issues one query per call and its range form one query for a whole window"
  - "Source identity (DASHBOARD-05, JOURNAL-06): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-SIGNAL-001, DASHBOARD-05) and (FEAT-SIGNAL-001, JOURNAL-06) note rows carry that source_identity_sha256"
  - "docs/product/07-MODEL-REGISTRY.md row MODEL-EXIT-001 names lib/signal_plan.py and the plan columns, python3 scripts/gate/export_model_registry.py is run and its JSON committed, the FEAT-SIGNAL-001 catalog record (Status, Last reviewed) and the PR traceability entry are updated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Signals carry their plan: entry, stop, T1 to T3 and the rule behind each, built once, stored on the row and scored in R

## Authority and status

Approved by the owner (T) on 2026-11-14 with: "Im fine with signal plan." That takes recommendations
1 to 7 of the draft as written; they are recorded below as decisions. No code is written under this spec
before it is on main.

On 2026-11-15 the owner answered the recommendation "split it" for PR #1950 with: "Yes do whats needed
to be completed". This revision moves the history attach to
`docs/superpowers/specs/2026-11-15-feat-signal-001-history-attach.md` and adds the `no_fill` outcome for
a signal on the session's last regular-hours bar; both are recorded as decision 8.

The request it answers (T, 2026-11-14), verbatim: "A signal should carry its full plan at the moment it
is created: entry, stop, T1 to T3, and the rule that produced each. That is what #1832 does for the
brief plan. The momentum signals and live alerts should get the same treatment, so that every signal can
be scored in R against its own stop". Also: "What is a signal if it doesn't have a target entry, tp
targets and stop loss", and "its good that price reaches the target".

With the approval the owner asked: "Signals carying their own plan means what? Should it create
everything in same fashion that brings the briefs and insights together?" The answer is yes, and it is
a requirement of this design, stated in Design 6: a signal's plan, the session's brief plan and the
insight read for the same ticker and session come from the same level set and the same builder, so they
cannot disagree about where a level is. Design 6 says what is already shared, the one place the insight
pipeline differs today, and what this spec adds.

Every statement below about code or data is marked "read" (read in the source, not executed) or "run"
(a query or command was executed; the execution name is in "Queries run"). Code references are to
origin/main at 515f8fde, which holds #1832 (its code is unchanged since ad0ba50f).

## Capability

FEAT-SIGNAL-001 owns this. Its row in `docs/product/02-FEATURE-CATALOG.md` (line 21):

> | [FEAT-SIGNAL-001](#feat-signal-001) | Signals / execution | Signal discovery, alerting, exits | `/signals`, `/live` | `/api/signals` | `signal_alerts`, `historical_signals`, `exit_config_overrides` | Production but needs remediation | P0 | 1 | 25 | [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#928](https://github.com/TeneikaAskew/stocks/issues/928) [#1206](https://github.com/TeneikaAskew/stocks/issues/1206) |

Two capabilities are involved. FEAT-SIGNAL-001 owns the signals, the live alerts, both tables and the
exit model (MODEL-EXIT-001), so it owns the plan a signal carries and its score. FEAT-STRAT-001 owns the
level builder in `lib/strat_levels.py` ("the one level builder: levels, side lists, broken status,
window, triggers, stops, targets and reason per side", its catalog record) and #1832. This spec calls
that builder and adds one entry-anchored call path to it; the brief's own output is pinned unchanged by
its existing tests. That is one spec under FEAT-SIGNAL-001, the way #1832 (FEAT-STRAT-001) changed
`gcp/signal_monitor.py` as a consumer. The work is split by what a user can see, not by capability,
and the history attach is a spec of its own: see "Size and split".

## Decisions (owner, 2026-11-14 and 2026-11-15)

Decisions 1 to 7 were decided on 2026-11-14 as recommended, and decision 8 on 2026-11-15. Each item
gives the decision in one line, then the evidence it rests on.

1. **The stop rule.** **Decided: the signal's stop is the nearest level on the other side of the entry,
   the brief's stop rule (`lib/strat_levels.py:2437-2438`, read); the signal bar's opposite side and an
   ATR multiple are also recorded on every signal.** The three options were (a) the signal bar's
   opposite side, (b) a multiple of ATR, (c) the level.
   - (a) gives an R that cannot be read. The exit evaluation scored its check days against the signal
     bar's opposite side and says: "R is in `final_tables/check_days.csv` but is not usable on these
     days: the stop is one 1-minute bar wide, so results read as tens or hundreds of R"
     (`signal-eval/report.md`, section 5 and section 7, "Noise").
   - (b) has no calibrated multiple for a 1-minute signal. The per-ticker `stop_*_atr` keys were
     calibrated for the planner's entry zones on daily ATR (`persona_stop_price`,
     `lib/strat_levels.py:1003-1028`, read). Whether they suit a momentum signal is not checked.
   - (c) is a named level, is the same kind of R the brief's plan is scored in, and is what "the same
     treatment" as #1832 means. Its cost: when no level passes the stop window the signal has no stop
     (pinned for the brief by `tests/lib/test_strat_levels_playbook.py::test_no_stop_when_no_fresh_opposite`),
     and a level stop can sit far from a signal fired mid-range. How often either happens for signals
     is not checked: no run has built level stops for signals.
   - Recording all three costs two numbers per row and lets the first clean run report, per rule, the
     share of signals with a stop and the size of 1 R in percent of price, so the choice can be changed
     with a version bump and no second pass over history.
2. **The target rule.** **Decided: targets are the next levels only, spaced by the ticker's
   `target_min_spacing_atr` as #1832 does; no ATR targets are stored.**
   Each target then has a level and a rule behind it, which is what was asked. ATR targets are not
   stored: in table D no ATR target exit passes the gate on any ticker, with a fixed or a trailing ATR
   stop (best fixed-stop exit, % per session, before and after 2026-05-01: SPY +0.051 and -0.002, QQQ
   +0.124 and +0.055, IWM +0.107 and -0.108), and the best multiple differs by ticker, so there is no
   multiple to store. An ATR target can still be evaluated later from the bars without a stored one.
3. **The exit plan to score.** **Decided: thirds at T1 to T3 are scored as `plan_r` (the #1832 shape)
   and all out at T1 beside it as `plan_r_t1`; no trail.** The evidence points two ways, so both are
   stored:
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
4. **A signal with no valid stop or no target.** **Decided: it is stored, never dropped, and the gap
   is never filled.** The missing price is NULL, `plan_status` names the first missing piece
   (`stop_unavailable`, `targets_unavailable`, `params_unavailable`, `levels_unavailable`,
   `atr_unavailable`, `extremes_incomplete`, `basis_replaced`, `outside_session`, `bar_mismatch`), and
   `plan_r` is NULL with a
   `plan_r_status`. The two statuses added after review (Design 1 and Design 2) follow the same
   decision. Rule 3.7: a level that does not exist is never replaced by a computed one. The live
   monitor already persists every fire whatever the Discord gate decides
   (`gcp/signal_monitor.py:1655-1676`, read).
5. **What live alerts post to Discord.** **Decided: no change in this spec; the row carries the plan
   from the first fire, and the embed changes in the second spec.** The monitor still exits on its
   percent target, time stop and RSI (`gcp/signal_monitor.py:2152-2164`, read) and has no stop per
   trade by a recorded decision (`lib/config.py:309-338`, read; issue #815). An embed that shows a
   stop and T1 to T3 would describe a trade the monitor does not manage, and thirds at level targets
   show no edge in table D.
6. **History.** **Decided: plans are attached to the stored signals of SPY, QQQ and IWM from
   2025-03-03 by update, with no delete and no regeneration; live alerts get plans from the deploy on
   and are not backfilled.**
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
     `params_unavailable`. So the attach waits until that calibration is written for the window, which
     is FEAT-STRAT-001's step and needs the owner's yes of its own. The local evaluation used its own
     local calibration.
   - Stored live alerts (3,146 live rows, run, db-query-t4nsl) keep NULL plans. A replay with
     `REPLAY_DATE` writes `run_kind='replay'` rows with plans for any date whose parameters exist.
7. **Where the split falls.** **Decided: two specs.** This one builds, stores and scores the plan
   and changes nothing a user sees. The second shows it: Discord embed, `/api/signals` fields, the
   OpenAPI snapshot, solyra types, fixtures and Playwright evidence. See "Size and split".
8. **The history attach and the last bar (2026-11-15).** **Decided: the history attach moves to a spec
   of its own, and a signal on the session's last regular-hours bar is scored `no_fill`.** The owner
   answered the recommendation "split it" for PR #1950 with: "Yes do whats needed to be completed".
   - The cut is the one "Size and split" named: the range parameter read, `--attach-plans` and the
     dry-run measurement move to `docs/superpowers/specs/2026-11-15-feat-signal-001-history-attach.md`,
     which is implemented after this spec, on the columns, `build_signal_plan` and
     `read_open_level_basis` this spec adds. Decision 6 is carried out there, and `bar_mismatch` in
     decision 4's list is written only by the attach. This makes three specs where decision 7 says
     two; decision 7's line between building the plan and showing it is unchanged.
   - The same approval takes the fix for the review finding on the last bar (Codex, PR #1950). Under
     `next-open-v1` a signal fills at the open of the next regular-hours bar of its session. A signal
     on the last regular-hours bar, 15:59 ET on a full day and 12:59 ET on a half day, has no such bar.
     Its outcome is the terminal `plan_r_status` `no_fill`, with no fill and no R, and the row is not
     pending (Design 4).

## Problem

A stored signal is a time, a direction and a price. It has no stop and, in history, no target, so it
cannot be scored in R, and every evaluation so far had to invent the plan afterwards.

What is true today:

- **`historical_signals`** holds ticker, entry_time, trade_type, entry_price, signal_strength,
  indicators at entry and best-case returns at fixed windows of 5 to 60 minutes
  (`gcp/schema.sql:2400-2433`, read), plus `realized_return_pct` under one fixed 20-minute exit
  (`:2453-2455`, read). No stop and no target: the three signal tables hold no column named like stop,
  plan, t1 or target except `signal_alerts.target_price` and `time_stop_minutes` (run, db-query-t4nsl).
  One correction to the request's wording: the schema comment says signal_strength is 3 to 5, but the
  generator on main needs 5 or more of 7 conditions (`lib/trading_analysis.py:995`, `:1069`, read) and
  the rows stored since 2026-10-01 hold 5, 6 and 7 only (run, db-query-8rb9b).
- **`signal_alerts`** holds direction, scores, price_at_signal, one `target_price`, `time_stop_minutes`
  and the exit columns (`gcp/schema.sql:1085-1118`, `:3931-3936`, read). The target is the signal price
  moved by a per-ticker percent, and the time stop is in minutes (`gcp/signal_monitor.py:1550-1556`,
  read). There is no stop price. Exits are target, time stop, RSI or a fixed horizon in the monitor
  (`:2119-2169`, read) and the same rules in the end-of-day resolver, which closes what is left at the
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
- The insight pipeline is not changed. It reads the brief's stored `level_basis` and the same builder
  but applies its own newer premarket snapshot, so its premarket levels, reference and picks can differ
  from the brief's (Design 6). Making the two use one snapshot is not done here: the one level source
  spec chose that step on purpose (the planner runs later than the 08:30 brief), the code is
  FEAT-INSIGHT-001's and FEAT-STRAT-001's, and the approved late slot already moves the brief's own
  basis to the 09:20 snapshot. Each side stores the basis it read, so the difference is a query.
- No read of the vendor's full intraday series to rebuild the monitor's session extremes after a late
  start. No session-complete read exists in the monitor today, and adding one is a new vendor call
  shape on the live path. A late monitor gives `extremes_incomplete` instead (Design 1).
- No recovery of a basis that was replaced after the open (Design 2). It needs a mark on the brief's
  history rows that reached the canonical row, which is FEAT-PLAYBOOK-001's writer.
- No change to `find_open_alerts`, the exit walk or the recompute's `--re-resolve`. The plan outcome
  has its own selection and its own columns.
- Replay rows are not scored, and an outcome already written is not rescored when bars are rewritten
  later. The outcome columns are derived only from the stored plan and the bars, so a later tool can
  rewrite them; none is added here.
- No new column for agreement between a signal and the brief or the insight. The columns exist
  (Design 6); the insight ones are filled by open PR #1823, not here.

## Approaches considered

1. **Reuse #1832's builder as is.** Not possible. `_pick_side` takes the first unbroken rung past the
   reference as the trigger and plans targets from that rung (`lib/strat_levels.py:2356-2443`,
   `_plan_targets` at `:2445`, read). A signal enters at the market on the next bar, so
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
| Entry | reference price: the signal bar's close. The fill is the next regular-hours bar's open and is known only at scoring; a signal on the session's last regular-hours bar has none (`no_fill`, Design 4) | `next-open-v1` |
| Stop | the nearest level on the other side of the reference that passes the stop window (decision 1), with its level name and timeframe; the bar-opposite and ATR stops as alternates | `level-other-side-v1`, `bar-opposite-v1`, `atr-multiple-v1` |
| T1 to T3 | the next levels past the cleared mark in the signal's direction, each at least `target_min_spacing_atr` x ATR past the entry or the target before it, up to `exit_legs` of them, each with level name and timeframe | `next-level-spaced-v1` |
| Legs | `exit_legs` from the policy (3), each 1/legs of the position | policy row |
| R unit | `risk_ref` = abs(reference minus stop) at creation; R at scoring is abs(fill minus stop) | stated in the record |
| Brief link | `brief_trigger`: the name and price of the brief's trigger for the signal's side, and whether it is this plan's stop, T1, T2, T3 or none of them (Design 6) | matched by level name and cent |

The cleared mark is the further of two prices: the builder's own mark for the session (its reference
and the accepted premarket extreme) and the regular-session high (for a call) or low (for a put) through
the signal bar. A level between the entry reference and that mark has already traded and is never a
target: the builder's existing broken rule, extended by the session's own bars.

**The session extremes must be complete, or there is no plan.** The monitor's extremes are not always
the session's. It fetches the last 100 one-minute bars on each poll (`outputsize: 'compact'`,
`gcp/signal_monitor.py:349`, read) and folds each batch into extremes that start empty (`:216`,
`:422-466`, read), so after a restart or a start more than 100 minutes into the session the earlier
bars are never seen. Run on 2026-11-14 with the real `_update_session_extremes`: a session high of 110
at 09:45 followed by 100 bars below 102 gives 110 from the full session and 101.9 from the last 100
bars, so a level at 105 is already traded for history and a full replay and still a call target for the
late monitor. The monitor has no other read of today's bars: a session's bars are stored at about
21:00 ET that evening (run, db-query-5sn5d). So the rule is the same in every writer: the extremes are
complete only when the bars folded reach back to the session's open (from the shared calendar) and no
batch started after the last bar already folded. Otherwise the plan is `extremes_incomplete` with every
price NULL. History and the replay apply the same rule to their frame. No vendor call is added to fill
the gap (Non-goals).

The record also holds the bar time, session date, the level source (`level_basis` or built), the level
rule version, the ATR basis and value, the reference and cleared marks, whether the extremes were
complete and the first bar they cover, each parameter used with its status, method and effective date,
and the builder's version (REQ-DATA-003).

### 2. Where it is computed

`lib/signal_plan.py` (new), two functions and the session-extremes helper they share:

- `build_signal_plan(direction, signal_bar, extremes, session_levels) -> SignalPlan`. The only place a
  signal's stop or target is computed. `extremes` holds the session's high and low through the signal
  bar and whether they are complete (Design 1); history and the replay derive it from their frame with
  the helper, and the monitor passes its own. It calls a new public entry-anchored function in
  `lib/strat_levels.py` that runs the existing side pick with the entry as the anchor rung and no
  cutoff requirement. A new file because neither `lib/signals.py` (conditions and scores) nor
  `lib/strat_levels.py` (session levels) is the home of bar-anchored entries and leg scoring; the plan
  may fold it into `lib/strat_levels.py` if review prefers.
- `score_signal_plan(plan, bars_after_signal) -> PlanOutcome`. The leg walk now inside `resolve_plan`
  (`gcp/premarket_playbook_resolver.py:473-585`, read) moves here and
  `resolve_plan` calls it, so the brief and the signals are scored by one walk. One stated difference:
  a signal fills at the entry bar's open, so that bar counts for targets as well as for the stop; the
  brief's call keeps its own value of that argument.

The three writers call `build_signal_plan` and nothing else:

- **History.** `scripts/run_historical_signals.py::_process_ticker`, after the signals frame exists
  and before `map_signals_to_table`, for both strategies. `lib/trading_analysis.py` is not changed.
  The history attach (its own spec, decision 8) reuses this step for stored rows.
- **Live.** A method `SignalMonitor._signal_plan(ticker, sig, latest)` takes the session's open basis
  (below; read once per ticker and session and kept), `self.session_extremes[ticker]` and its coverage
  (`gcp/signal_monitor.py:422-466`, read), is called in `fire_alert`, and its result is passed to
  `_persist_signal_alert`.
- **Replay.** The capture function calls the same `_signal_plan`, `FireRecord` carries the plan, and
  the replay's insert writes the plan columns.

**Which basis a signal gets: the one in force at the session's open, proven, or none.** The canonical
brief row is not fixed for the day. The approved late slot rewrites it at about 09:20 and moves
`analysis_ts` (its decisions C and D), and an operator's `--update` or `BRIEF_UPDATE` run overwrites it
at any time and is stamped live (`gcp/premarket_brief.py:3076-3077`, `:3293`, `:3309-3313`, read).
Reading "the current live basis" would give an earlier signal levels that did not exist when it fired.
So every writer reads
the basis through one new reader, `read_open_level_basis(query_fn, ticker, session_date)` in
`lib/strat_levels.py`, with a range form for a window, and it answers one of three things:

- **the open basis**: the canonical live row's basis, when `premarket_analysis_history` holds a row of
  the same build (`level_basis.built_at`) written at or before the session's regular open. Each brief
  run appends its row to history before it writes the canonical row (`:3274`, then `:3309`, read), and
  any later overwrite carries a later build, so a canonical basis whose own history row predates the
  open has been in force since before the open.
- **no stored basis**: no live brief run stored a basis for the session. The builder is used, as the
  monitor does today (`gcp/signal_monitor.py:978-984`, read), and the plan records `built`.
- **`basis_replaced`**: a live basis was stored for the session, but the canonical live row no longer
  holds a build proven to predate the open (an overwrite after the open, or a replay row in its
  place). The plan is unavailable with every price NULL. It is never built from the replacement and
  never rebuilt.

What this gives. A signal at 09:35 and one at 14:00 get the same basis: the late slot's when its write
landed before the open (its cutoff is 09:29:30), else the 08:30 one. No planned signal sits before the
late write, because a plan exists only for a regular-session bar. That is also what the monitor does
on a normal day: it reads the levels once after 09:30 and keeps them (`gcp/signal_monitor.py:1254-1255`,
read). A basis replaced after the open is used by no signal of that session. A live alert planned
before the replacement keeps the plan it was given; history and a later replay of that session say
`basis_replaced`; so the same bar never carries two different plans.

The earlier basis does survive in `premarket_analysis_history`, which is append-only and holds
`level_basis` (`gcp/schema.sql:2187-2188`, read). It is not picked from there by time, because history
also holds builds that never reached the canonical row: on 2026-11-13 it holds the 08:30:53 scheduled
row, whose build is the canonical one, and a 10:32:02 row whose build is not (run, db-query-5sn5d).
Picking "the last row before the signal" would be wrong. Recovering a replaced basis needs a mark on
the history rows that did reach the canonical row; that is the brief writer's and is not added here
(Non-goals). The cost is small today: for SPY since 2026-05-01 the brief history holds `manual_update`
rows on one date, a Saturday, and replay rows on 16 dates, most written on a later day (run,
db-query-zf2x4).

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

On the signal's own row. The plan is written when the signal is created; the outcome is written later
by a pass that selects rows by the plan alone (below):

| Column | Type | Meaning |
|---|---|---|
| `plan_fill_price` | DOUBLE PRECISION | the open of the next regular-hours bar after the signal bar, same session; NULL for `no_fill` |
| `plan_r` | DOUBLE PRECISION | mean over legs of sign x (exit minus fill) / abs(fill minus stop), gross, no costs; NULL unless `plan_r_status` is `ok` |
| `plan_r_t1` | DOUBLE PRECISION | the same with every leg out at T1 (decision 3); NULL unless `plan_r_status` is `ok` |
| `plan_r_status` | VARCHAR(24) | NULL while the row waits to be scored; then `ok`, `stop_unavailable`, `targets_unavailable`, `invalid_stop` or `no_fill`. A row whose plan has no prices gets `no_plan` when it is created. Every value is terminal |
| `plan_exit` | VARCHAR(32) | the legs' exits in order, for example `t1,t2,close`; NULL for `no_fill` |
| `plan_t1_hit_ts` to `plan_t3_hit_ts` | TIMESTAMPTZ | first bar at or after the fill that reaches each target, whatever the legs did; NULL when there is no fill |
| `plan_score_rule` | VARCHAR(32) | `signal-legs-v1` |

Within the walk a target fills at its price, the stop at its price or at a later bar's open beyond it,
a bar touching both counts the stop first, and legs still open exit at the last regular-hours close:
#1832's rules.

**A signal on the session's last regular-hours bar has no fill.** `next-open-v1` fills at the open of
the next regular-hours bar of the same session. The session's close comes from the shared calendar,
`lib.eastern_time.session_close` (`lib/eastern_time.py:784`, read; run on 2026-11-15, it gives 16:00 ET
for 2026-11-13 and 13:00 ET for 2026-11-27 and 2026-12-24), so the last regular-hours bar is the 15:59
ET bar on a full day and the 12:59 ET bar on a half day. A signal on that bar has nothing to fill at:
an extended-hours bar after the close, or the next session's open, is never a fill. `score_signal_plan`
gives it `plan_r_status` `no_fill`, with `plan_fill_price`, `plan_r`, `plan_r_t1`, `plan_exit` and the
three hit timestamps NULL. The plan columns keep what was built at the bar. `no_fill` is an outcome,
not a wait: like every other value it ends the row's pending state, so no pass selects it again and it
never counts as a row left pending. `VARCHAR(24)` holds it.

**Which rows are scored: every row with a plan and no outcome, whatever else has happened to it.** A
row is pending when `plan_version` is set and `plan_r_status` is NULL. Scoring selects on that and on
nothing else. Any `plan_r_status` value, `no_fill` included, ends the wait and takes the row out of the
partial index.

- **`signal_alerts`.** The end-of-day resolver's own selection cannot be used. It takes
  `is_open IS TRUE OR exit_ts IS NULL` (`gcp/signal_monitor_eod_resolver.py:143-144`, read), and the
  monitor closes most alerts itself, setting `is_open = FALSE` and `exit_ts`
  (`gcp/signal_monitor.py:2464-2473`, read): 2,311 of the 3,146 live exits were written by the monitor
  (the recompute spec, section 3, run there), and from 2026-09-28 on the resolver closed 10. `run()`
  also returns as soon as nothing is open. Adding columns to its UPDATE would leave nearly every alert
  unscored. So the resolver job gets a second pass with its own selection,
  `find_alerts_pending_plan`: live rows with a plan and no outcome inside the heal window (10 days by
  default), one strict query with no `is_open` and no `exit_ts` in it, served by a partial index on
  the pending predicate. The pass runs on every execution, also when there is nothing to resolve, and
  writes only the outcome columns, in one UPDATE per ticker and session. It does not touch `exit_*`,
  `is_open` or `trades`, and `find_open_alerts` and the exit walk are not changed.
- **When.** A session's bars are stored at about 21:00 ET (run, db-query-5sn5d), after the resolver's
  16:30 run, so an alert's outcome is written by the next session's run. Today's rows stay pending and
  that is not a failure, the rule the resolver already applies to a same-day skip
  (`gcp/signal_monitor_eod_resolver.py:527-538`, read). A row of an earlier session that is still
  pending after the pass (its bars are missing or stop short of the close) makes the job exit nonzero.
  An alert on its session's last regular-hours bar is scored like any other once its session's bars
  are read, and ends `no_fill`, which is not pending.
- **`historical_signals`.** The same shape. The generator inserts the row with its plan; the outcome is
  written by a pass in the same run over the pending rows of its tickers inside the heal window (7
  days), so a row inserted while its session was incomplete is scored by a later run and is not left
  out because `ON CONFLICT DO NOTHING` never revisits it. A row still pending for a session before the
  last complete one fails the run; a row on its session's last regular-hours bar ends `no_fill` and
  does not. Rows stored before plans existed have `plan_version` NULL, so this pass never selects them;
  the history attach (its own spec, decision 8) gives them their plan and outcome.
- Replay rows carry the plan and are not scored by these passes.

### 5. Reads and writes (Rule 0)

- Monitor: one read of the open basis per ticker and session, at the first fire (3 a session for SPY,
  QQQ and IWM), and none on any later fire or on any bar. One `build_signal_plan` call per fire.
- Resolver job, per run: one selection of pending alerts, one bar read per ticker and session that has
  pending alerts (3 on a normal day, shared with the exit pass through its per-run cache), and one
  UPDATE per ticker and session. Nothing per alert.
- Nightly generator, per run: four more reads for the whole run (level parameters for the session, the
  open basis of each ticker, daily rows with their premarket fields, the pending rows of the heal
  window, each for all tickers in one query), none per signal or per ticker, and one UPDATE per 1,000
  outcomes.

### 6. One level set for the brief, the insight read and the signal

The owner's question, "Should it create everything in same fashion that brings the briefs and insights
together?": yes. A signal's plan is not a third opinion about the levels. It is built from the session's
level set by the builder the brief and the insight already use, and it says so on the row.

**Already shared today** (read, on main at ad0ba50f):

- One builder. `build_session_levels` (`lib/strat_levels.py:2147`) makes the levels, side lists,
  triggers, stops and targets for every consumer.
- One stored set per session. The brief writes its `SessionLevels` as `level_basis` on its
  `premarket_analysis` row (`gcp/premarket_brief.py:1379`, `:3241`; column at `gcp/schema.sql:2186`).
- The monitor reads that stored basis for the session and rebuilds from it, and builds with the same
  builder only when no live row exists (`gcp/signal_monitor.py:853`, `:978-984`).
- The insight pipeline reads the same stored basis through the same reader
  (`lib/agents/summarizers.py:601-603`, `read_live_level_basis` at `lib/strat_levels.py:2560`), builds
  with the same builder when there is none (`:612-614`), plans from it
  (`lib/agents/trade_planner.py:616-622`) and stores the basis it used in its report
  (`lib/agents/orchestrator.py:589-593`, `:674`).

**One difference in the insight pipeline.** After reading the brief's basis it applies its own newer
premarket snapshot (`lib/agents/summarizers.py:604-605`). `with_premarket` "replaces the premarket high
and low candidates and the reference, keeps every structural level, and recomputes broken status and
picks" (`lib/strat_levels.py:1669-1681`). So the brief and the insight cannot disagree about a prior
day, week, month, quarter or year level or the parent bar, but they can hold different premarket highs
and lows, and so a different trigger, when the insight runs on a later snapshot. The insight's stop is
also a different rule on the same levels: an ATR distance from its entry zone with the builder's stop as
one anchor (`lib/agents/trade_planner.py:118-135`, `:279`). This spec does not change either (Non-goals).
The signal's plan follows the monitor: the stored basis as written, with no snapshot of its own.

**What `signal_alerts` already records about agreement** (columns read in `gcp/schema.sql`, fill rates
run, db-query-9zsrl, 3,146 live alerts):

| Columns | Where the monitor fills them | Filled today |
|---|---|---|
| `brief_bias`, `brief_alignment`, `brief_setup_count` (`gcp/schema.sql:3975-3977`) | `_resolve_brief_alignment` and `_resolve_brief_bias` (`gcp/signal_monitor.py:1931`, `:2097`), written at `:1763-1765` | 2,395, 511 and 2,395 rows; alignment is aligned 269, opposed 209, invalidated 33 |
| `level_state`, `opp_level_state` (`:4066`, `:4068`) | `_resolve_level_state` (`:2074`), written at `:1775-1776` | `level_state` on 635 rows |
| `insight_direction`, `insight_conviction`, `insight_regime`, `gate_action`, `gate_reason`, `thesis_invalidated` (`:4036-4041`) | nowhere on main. The gate reads the insight and decides (`gcp/signal_monitor.py:1401-1423`) but `_persist_signal_alert` (`:1697`) writes none of the six | 0 rows for each of the first five (run). Open PR #1823 fills them |

So a live alert already says whether it agrees with the brief's bias and, once #1823 is on main, what the
insight said. What no row says is which levels the signal's own stop and targets are.

**What this spec adds:**

- The plan names the level behind its stop and behind each of T1 to T3 by the builder's level names, the
  names the brief stores in `calls_trigger_name`, `calls_stop_name` and their put twins
  (`gcp/schema.sql:1885-1892`) and in `level_basis`.
- `plan.levels` records where the level set came from: `level_basis` with its rule version and build
  time, or `built` when the session has no stored basis. When a stored basis exists every writer builds
  the plan from the one in force at the open (Design 2), history included, so a signal and the brief
  of the same session cannot place a level differently, a level the brief does not hold cannot appear
  in a plan, and a basis written after the open is never used.
- `plan.brief_trigger` records the brief's trigger for the signal's side (name and price) and its role
  in this plan: `stop`, `t1`, `t2`, `t3` or `none`; `not_published` when the brief gave that side no
  trigger; NULL when there is no stored basis.

`tests/gcp/test_signal_plan_level_source.py::test_plan_levels_come_from_the_brief_basis` holds all three,
and `::TestOpenBasis` holds the rule for a basis that is replaced.

## Order against work in progress

Checked again on 2026-11-14 after the review of this spec (GitHub and the refs, read):

1. **Clean bars.** No stored signal is given a plan or scored before the month replace and rebuilds
   planned for 2026-11-14 and 11-15 are done and verified, and `historical_signals` has been
   regenerated on those bars by the runbook (REQ-VALID-001). Code and tests may land before; the
   history attach's run (its own spec) and any scored figure may not.
2. **#1832 on main: met.** #1832 merged on 2026-11-14 at 20:04:55Z as ad0ba50f (the approval message
   still called it open; GitHub and origin/main show it merged). Its spacing, legs, `gate_targets`
   split and leg walk are what this spec reuses, and every reference above is to that commit.

Files this spec would touch: `lib/signal_plan.py` (new), `lib/strat_levels.py`,
`gcp/premarket_playbook_resolver.py`, `gcp/schema.sql`, `gcp/historical_signals.py`,
`scripts/run_historical_signals.py`, `gcp/signal_monitor.py`, `scripts/replay_signal_monitor.py`,
`gcp/signal_monitor_eod_resolver.py`, their tests, `docs/product/07-MODEL-REGISTRY.md` (one row) and
the FEAT-SIGNAL-001 catalog and traceability entries.

| Open work | Files it changes outside docs and tests | Overlap with this spec | Order that avoids a conflict |
|---|---|---|---|
| `fix/feat-data-001-deployed-dates-exchange-clock`, PR #1948 (open, head now 5daccb8f) | 39 files, among them `gcp/signal_monitor.py` (lines 36 and 381, unchanged on the new head), `lib/trading_analysis.py`, `lib/strategies/exit_config_overrides.py`, `gcp/trade_logger.py` | `gcp/signal_monitor.py`, different hunks (this spec changes `fire_alert` and `_persist_signal_alert`, lines 1450 to 1872). Nothing else: this spec does not change `lib/trading_analysis.py` | #1948 merges first; this branch is cut after |
| `feature/feat-data-001-recompute-after-bar-rewrite` (local branch, e2ba7f7b, 15 commits ahead of main and 3 behind, still not on origin) | `gcp/bar_recompute.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/gcs_utils.py`, `gcp/schema.sql`, `gcp/signal_monitor_eod_resolver.py` | **Two files.** `gcp/schema.sql`: both append at the end of the file. `gcp/signal_monitor_eod_resolver.py`: it rewrites the exit walk and adds `find_resolved_alerts`; this spec adds a separate pending-plan pass beside both and changes neither | The recompute merges first. This spec's pass is written against its file |
| `feature/feat-playbook-001-brief-late-slot` (local, one commit so far: its plan document) | by its spec, only `gcp/premarket_brief.py` and `gcp/fetchers/fetch_premarket_refresh.py` | none in files. In data: it rewrites the day's `level_basis` at 09:20, which the monitor reads; the plan records the level source it used | none needed |
| The replace-tool fix: spec PR #1949 (merged, 515f8fde, one document) and the code that follows it | the PR changed no code; the fix is in `gcp/fetchers/fetch_alphavantage_intraday.py` | none | none needed |
| PR #1951, FEAT-STRAT-001 ATR levels on the brief (open, head 1cbc2b1b; opened after the approval) | `lib/strat_levels.py` (many hunks, `SessionLevels` and the candidate rungs among them) and `gcp/schema.sql` (the policy rows) | both files. Its ATR levels are display only by its title; the plan reads the builder's candidate list | #1951 merges first, or this branch rebases on it before review |
| PR #1832 (merged, ad0ba50f) | `lib/strat_levels.py`, `gcp/premarket_playbook_resolver.py`, `gcp/schema.sql`, `gcp/signal_monitor.py`, `gcp/premarket_brief.py`, `lib/level_calibration.py`, `lib/agents/summarizers.py` | four files, by design | done: it is on main |
| PR #1823, FEAT-SIGNAL-001 gate decision record (open, head 15044ddf; not in the list given) | `gcp/signal_monitor.py`: the gate block and the row in `_persist_signal_alert` | the same function, and it fills the six insight and gate columns Design 6 names | #1823 merges first, or this branch rebases on it before review |

So the answer to "none of them is touched" is no for two of the four named: #1948 shares one file in
different hunks, and the recompute branch shares two files. Cutting this branch after #1948, the
recompute, #1823 and #1951 are on main avoids every conflict. With #1832 merged, nothing else holds the
code back.

## Size and split

About 26 tasks in all, in three specs (decisions 7 and 8).

- **This spec, about 15 tasks: carry and score.** The entry-anchored call path; `build_signal_plan`;
  the look-ahead tests; `score_signal_plan`, with the `no_fill` outcome, and the brief resolver on it;
  the open-basis reader and its range form (added after review); the columns and the pending index;
  the generator step with its pending pass; the monitor; the extremes coverage rule and the
  late-start parity cases (added after review); the replay; the parity and single-source tests; the
  brief link and the level-source test; the resolver's pending-plan pass with its run-level suite
  (grown after review); the unchanged-surface tests; the registry row, product records and source
  identity.
- **The history attach, about 3 tasks: attach to stored rows.** The range parameter read,
  `--attach-plans` and the dry-run measurement, in
  `docs/superpowers/specs/2026-11-15-feat-signal-001-history-attach.md`, with its own product records
  and source identity. It is implemented after this spec, on the columns, `build_signal_plan` and
  `read_open_level_basis` added here.
- **Second spec, about 8 tasks: show.** The Discord embed, plan and R fields on
  `/api/signals/{ticker}` and `/similar` with an API test of the changed response and the regenerated
  OpenAPI snapshot, solyra's types, fixtures, hermetic Playwright evidence and the cloud spec, and R in
  the weekly quality report. It starts after the first scored month exists, so what is shown has been
  measured.

This spec held about 18 tasks, over the skill's line of about 15, and the review added two of them. The
cut is the history attach, made on 2026-11-15 with the owner's yes (decision 8). This spec was not yet
on main, so the cut is made in its own pull request and no superseding spec is needed. Two `done_when`
items moved whole: `test_attach_plans` and the dry-run numbers in the PR body. Two lost their attach
part, which moved with them: `test_query_shape` keeps the nightly generator's reads here, and
`TestOpenBasis` keeps the history step and the monitor here. About 15 tasks remain here. The cut costs
no time, because the attach cannot run before the clean bars and the level parameters exist.

The line between this spec and the second: nothing a user can see changes in this one, and
`tests/api/test_signal_plan_not_served.py` holds that at the API.

## Capacity and cost

Estimates are marked; nothing below was measured for this design except where a file is named.

The history attach's run, and the regeneration it avoids, are sized in its own spec (decision 8).

**Nightly generator:** up to 25 tickers; 4 more reads a run; a few hundred plans and outcomes; seconds
(estimate). No new scheduled job, so no new monthly cost line. **Monitor:** about 23 fires a day (3,146
live alerts over the 137 sessions from 2026-05-01 to 2026-11-13, run); 3 basis reads a session and one
in-memory call per fire. **Resolver job:** about 23 pending alerts a run; 1 selection, 3 bar reads of
one session each and 3 UPDATEs, so about 7 round trips at 0.5 to 2 s, 4 to 14 s a run (estimate)
against its task timeout; the bar reads are the size the exit pass already makes for an open alert.

## Close-out

After the merge, recorded on the PR, each with its execution name:

1. The owner's yes for the column apply, then `gcp/apply_schema.py`; a query of
   `information_schema.columns` shows the 17 columns on each table.
2. Deploy. The next live fire's row: `SELECT plan_version, plan_status, plan_stop_price,
   plan_t1_price FROM signal_alerts WHERE alert_date = <day> AND run_kind = 'live'`. The resolver run
   of the next session fills `plan_r_status` on every such row, the ones the monitor closed included:
   `SELECT count(*), count(plan_r_status), count(*) FILTER (WHERE is_open IS FALSE AND plan_r_status
   IS NULL) FROM signal_alerts WHERE alert_date = <day> AND run_kind = 'live' AND plan_version IS NOT
   NULL` gives equal first and second counts and 0 for the third. An alert on the session's last
   regular-hours bar counts as scored, with `no_fill`.
3. Replay of that day through the production path (`REPLAY_DATE`). Its fire records carry the plan;
   they are compared with that day's live rows by ticker and the plan's bar time. Expected: no
   difference; any difference is listed with the inputs each side recorded.
4. The next nightly generator run writes plans on its new `historical_signals` rows.
5. Canvas refresh pending for the models diagram, run from chat after the merge.

The attach run over stored history, and the per-ticker and per-stop-rule figures it gives, are the
history attach spec's close-out (decision 8).

Source identity. `lib/`, `gcp/`, `scripts/` and `tests/` are inside SITE's watched scope. DASHBOARD-05
(the live signals table) reads `historical_signals` from the generator this changes, and JOURNAL-06 (the
trade table) reads `signal_alerts` from the monitor this changes. Only the
`(FEAT-SIGNAL-001, DASHBOARD-05)` and `(FEAT-SIGNAL-001, JOURNAL-06)` rows of the Implementation-source
notes table may describe this implementation, as backend source and local tests only; nothing either
element shows changes. Every other SITE byte stays unchanged. The declaration is made here because an
implementation PR cannot add it (open PR #1823 is red on the spec gate for that reason). After the
merge, separately and never as a pre-merge box: main's source and body identity verified in a fresh
clone, the DOC main and staging close-out with the evidence of steps 1 to 4, the sidecar retired as the
product-delivery skill prescribes, and the plan set to `status: done` on a `docs/` branch.

## Risks

- **History and live get different inputs for the same bar.** The function is shared; the session's
  levels and the cleared mark are read from different places (stored basis and the monitor's bars, or
  the full bar frame). The plan records its reference, cleared marks and level source, the parity test
  pins the function, and close-out step 3 measures the inputs on a real day.
- **A monitor restart costs the rest of that day's live plans.** After a start more than 100 minutes
  into the session every fire is `extremes_incomplete`. How often the monitor starts late is not
  checked. The count is a query on `plan_status` from the first week on.
- **A sub-second race at the open.** The proof of the open basis reads history's write time, and a
  brief run writes history a moment before the canonical row. A monitor reading between the two at
  09:30:00 could hold the earlier basis while the rule names the later one. The monitor reads at its
  first fire, not at the open, and the late slot's cutoff is 30 s before the open; an operator's update
  in that second is the remaining case, and the plan records the build it used.
- **Live outcomes arrive a session late**, and Friday's on Monday. Nothing reads them before the second
  spec.
- **Most early signals may have no stop.** Decision 1's cost. The alternates on every row, and the
  history attach spec's close-out, measure it before anyone relies on `plan_r`.
- **Look-ahead through the levels.** A daily row for the session itself, or a `level_basis` rewritten
  later in the day, would leak. The look-ahead test bounds the daily frame; the record keeps the basis
  it read.
- **The brief's scoring moves when its walk is extracted.** Held by its test file passing unchanged.
- **A plan reads as advice.** Nothing shows it until the second spec, and thirds at level targets have
  shown no edge so far.

## What was not verified

- How often a signal has a level stop, a spaced T1, or all three targets: not checked. No run has
  built plans for signals with the production builder.
- The speed of `build_signal_plan` and `score_signal_plan`: not checked.
- Whether the newest bar the monitor fires on is a finished minute or one still forming at the vendor:
  not checked. It would change the entry reference and the bar-opposite alternate, not a level.
- How often the monitor starts late or its feed breaks for more than 100 minutes: not checked.
- The replace-tool fix's own diff: not checked; only the file named in the request and that spec PR
  #1949 changes one document.
- That #1823's head still applies to today's main: not checked; its diff was read against its own base.
- Whether #1832's research figures hold on as-traded bars: not checked (the evaluation says the same).
- The bars' agreement with the vendor: not checked here; this spec waits for that verification.

## Queries run

Read-only, no `--commit`, 2026-11-14:

- `db-query-t4nsl`: row counts of `historical_signals` and `signal_alerts` by ticker and run kind;
  columns named like stop, plan, t1 or target on the three signal tables.
- `db-query-8ptk7`: `ticker_level_params` coverage for SPY, QQQ and IWM; `level_basis` coverage of
  `premarket_analysis`; `signal_metrics` counts; `level_param_policy` keys (25, none of #1832's yet).
- `db-query-8rb9b`: stored signal strengths since 2026-10-01; live exit reasons.
- `db-query-9zsrl`: how many live alerts hold each brief, level-state, insight and gate column.
- `db-query-5sn5d`: the brief history rows of SPY from 2026-11-10 beside the canonical build; when
  each session's 1-minute bars were stored.
- `db-query-zf2x4`: brief history rows of SPY since 2026-05-01 by run kind and by whether they were
  written after the open.

Also run, no database: the real `SignalMonitor._update_session_extremes` on a full session and on its
last 100 bars (Design 1); the script is a session file, not in the repo. On 2026-11-15,
`lib.eastern_time.session_close` for 2026-11-13, 2026-11-27 and 2026-12-24 (Design 4): 16:00, 13:00
and 13:00 ET.
