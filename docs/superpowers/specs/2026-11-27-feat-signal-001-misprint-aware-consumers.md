---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-DATA-001, REQ-DATA-003, REQ-REL-001, REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002]
issues: [915]
canvases: []
done_when:
  - "tests/lib/test_bar_prints_consumers.py passes for lib.bar_prints.touch_extremes(bars): over one ticker's regular-session bars of one day (ts ascending, open, high, low, close) it returns a frame in input order with ts, touch_high, touch_low, high_flagged, low_flagged and judged under rule touch-extremes-v1: a bar is judged when two bars follow it in the input; its reference on each side is print_geometry's (the opens and closes of the two bars on each side and its own open or close where that is not the extreme); its scale is the median of high minus low over the up-to-61 input bars ending two bars after it, fewer at the start of the input; its threshold is max(6 x scale, 0.0050 x reference); a judged bar's touch_high is its stored high unless the high exceeds the bound, in which case it is the reference, and the low mirrors it; an unjudged bar has NaN touch values and judged false; no stored value is changed and the function writes nothing; TOUCH_RULE_VERSION is 'touch-extremes-v1' and TOUCH_PARAMS is {'neighbours': 2, 'scale_bars': 61, 'scale_multiple': 6.0, 'floor_bp': 50.0} (on main the function does not exist)"
  - "tests/lib/test_bar_prints_consumers.py::test_agreement_with_stored_flags passes and prints the counts: over the ten known sessions and the clean sample in tests/fixtures/bar_prints/, the regular-session bar-sides touch_extremes flags beside those isolated_prints flags, with every difference named bar by bar; and over a changing-volatility fixture written in the test (60 bars of 0.05 range, then 60 bars of 0.60 range, with one 60 bp wick in the quiet half and one in the loud half), the two rules' decisions are listed side by side, the causal rule flags the quiet-half wick and not the loud-half one, and touch_extremes over the whole fixture equals touch_extremes over every prefix of it that holds the bar and two followers, bar for bar (parity of incremental and whole-session evaluation)"
  - "tests/lib/test_strat_levels.py::TestLegStateTrackerMisprints passes: LegStateTracker.update called with a bar whose stored high crosses the call trigger while its touch_high does not leaves the call leg 'fresh'; a triggered put whose stored high crosses the put stop while its touch_high does not stays not invalidated, and the same bar with touch_high equal to the stored high invalidates it; a triggered call whose stored low crosses the call stop while its touch_low does not stays not invalidated, and the unflagged bar invalidates it; tests/lib/test_strat_levels.py otherwise passes with no change against origin/main for the tracker's existing cases"
  - "tests/gcp/test_signal_monitor_misprints.py passes: SignalMonitor folds a polled snapshot into the leg trackers and the session extremes only for the regular-session bars that lib.bar_prints.touch_extremes judges over the snapshot's regular-session bars, using their touch_high and touch_low, so the two newest bars of every poll are folded on a later poll once judged and never before; over a fixture built from SPY 2026-11-04 bars the 10:00 bar's stored high 775.64 never advances the session high past 768.27 and never marks a call target reached, while the same run over the fixture with that high set to 768.24 produces identical leg states and extremes; over a snapshot delivered in three overlapping polls the leg states equal those of one whole-session fold (REQ-REL-001); a poll whose snapshot holds fewer than three regular-session bars folds nothing and logs one line; the fire path, _check_exits, the indicator window and every other reader of the snapshot are unchanged (git diff origin/main on their tests is empty)"
  - "tests/gcp/test_premarket_playbook_resolver.py::TestMisprints passes: resolve_leg, _traded_exit and resolve_plan walk the session's touch_high and touch_low from lib.bar_prints.touch_extremes over the day's regular-session bars read with two bars of margin after the close, so a flagged wick never fills, never reaches a target and never hits a stop; the four cases of SPY 2026-10-16, SPY 2026-11-04, SPY 2026-11-05 and IWM 2026-10-16 from the bucket copy, written out in the test with their stored and clean outcomes, resolve to the clean outcome; every outcome row records misprint_rule = lib.bar_prints.TOUCH_RULE_VERSION and misprints_ignored (the count of flagged bar-sides inside the session); RESOLVER_VERSION is bumped and the existing columns of a session with no flag are byte for byte as on main over the resolver's existing fixtures"
  - "tests/gcp/test_signal_monitor_eod_resolver.py passes with no change to the file against origin/main: the EOD resolver's exit walk (_detect_exit) and SignalMonitor._check_exits compare the bar's close to the target and read no high or low, and this spec leaves both as they are; tests/meta/test_bar_touch_single_source.py (item 8) asserts that gcp/signal_monitor_eod_resolver.py still reads no high or low for an exit decision"
  - "tests/gcp/test_replay_misprints.py passes: scripts/replay_signal_monitor.py and REPLAY_DATE feed the monitor the stored bars unchanged and the monitor applies the same helper it applies live, so the replay of SPY 2026-11-04 produces the same leg states as the live fixture of item 3 (REQ-REL-001, REQ-REPLAY-001)"
  - "gcp/schema.sql adds, with ADD COLUMN IF NOT EXISTS, nullable and with no default, misprint_rule VARCHAR(32) and misprints_ignored INTEGER on premarket_analysis and premarket_analysis_history; tests/gcp/test_misprint_columns_schema.py passes and the CREATE TABLE of market_data_intraday, intraday_bar_flags, intraday_bar_flag_coverage and signal_alerts are byte for byte as on main"
  - "tests/meta/test_bar_touch_single_source.py passes: by AST, no function in gcp/signal_monitor.py, gcp/premarket_playbook_resolver.py or scripts/replay_signal_monitor.py compares a bar's stored high or low against a trigger, target or stop price; every such comparison reads touch_high or touch_low; and gcp/signal_monitor_eod_resolver.py reads no bar high or low in _detect_exit"
  - "The PR body gives: the shipped helper run over the bucket copy of the three tickers for 2026-09-01 to 2026-11-18, listing every regular-hours bar-side it flags with the trigger, stop, target or guide it crosses on the day's stored level_basis, beside the nine bars this spec's Problem names, and the count of resolved premarket_analysis rows for that window whose entry_status, exit_reason or plan_r changes under the clean walk, computed read-only through scripts/db_query_cr.sh with its execution id; and the measured seconds of touch_extremes over one 100-bar snapshot and over one 390-bar session"
  - "make test passes on the PR head with isolated_prints, print_geometry, RULE_VERSION and PARAMS in lib/bar_prints.py unchanged against origin/main (the diff of that file adds touch_extremes, TOUCH_RULE_VERSION and TOUCH_PARAMS and changes no existing line), and with gcp/fetchers/intraday_bar_flags.py, gcp/fetchers/fetch_alphavantage_intraday.py, lib/indicators.py, gcp/signal_monitor_eod_resolver.py and lib/strat_levels.py's level builder (build_session_levels and everything it calls) not in the PR's diff, and tests/meta/test_production_writers.py unmodified"
  - "02-FEATURE-CATALOG FEAT-SIGNAL-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Misprint-aware consumers: the signal monitor, the resolvers and replay honour isolated-print-v1

## Problem

The stored 1-minute bars of SPY, QQQ and IWM hold prints that sit far outside their own minute. PR #2001 (FEAT-DATA-001, merged 2026-11-17, spec `docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md`) flags them under rule `isolated-print-v1` into `intraday_bar_flags`, with 143 months a ticker judged in production as of 2026-11-27 (coverage rows for all three tickers, `checked_at` 2026-11-27 02:01 UTC, db-query-5jr2x, read-only). That spec changed no consumer on purpose and left this spec to decide how each one honours the flags.

Today every consumer folds the stored high and low raw:

- `gcp/signal_monitor.py` `_update_session_extremes` (`:449-468` on main) takes `bars['High'].max()` and `bars['Low'].min()`; `_advance_leg_state` (`:668-724`) folds each bar's high and low into `lib.strat_levels.LegStateTracker.update`, which marks a leg triggered, past T1 or invalidated on a touch.
- `gcp/premarket_playbook_resolver.py` `_traded_exit` (`:403-466`) and `resolve_plan` (`:480`) fill, reach targets and hit stops on `bars['high']` and `bars['low']` read from `market_data_intraday` (`:738`).
- `gcp/signal_monitor_eod_resolver.py` builds `High` and `Low` from the same table (`:611-641`) and walks exits on them.
- `scripts/replay_signal_monitor.py` and `REPLAY_DATE` feed the monitor the stored bars, so a replay inherits the same touches.

The vendor still carries the prints. AlphaVantage's own copy of SPY 2026-11-04 10:00 today reads high 775.64 on a bar that opened 767.26 and closed 768.03 (TIME_SERIES_INTRADAY, 2026-11-27); Webull's bar for the same minute reads high 768.24 on the same volume. Nine such bars fall inside the 2026-09-01 to 2026-11-18 window of the intraday-forecast research (#2128); seven of them alone cross a trigger, a stop, a target or an ATR guide of that day's stored `level_basis` that no real trade reached (IWM 2026-10-16 12:54 crosses the put trigger 275.08 and the call stop 275.19; SPY 2026-10-16 12:53 crosses the put trigger 771.79, the call stop 772.87 and the put T1 769.63; SPY 2026-11-04 10:00 crosses the call T2 773.36). Under the production rule five of the nine are flagged (both 10-16 bars, SPY 10-30 14:28, SPY 11-04 10:00, SPY 11-05 13:10); four QQQ bars (10-15 10:50, 11-05 10:10, 11-12 09:54, 11-16 10:11) are not, and that is a rule-threshold question for FEAT-DATA-001, recorded below, not for this spec.

So a leg tracker can read 'triggered' or 'invalidated' off a print nobody traded, a resolved row can book a fill, a target or a stop that never happened, and a replay reproduces it faithfully. Issue #915 (same-minute ordering ambiguity) sits on the same walk.

## Non-goals

- No change to the rule, its parameters or the flag tables (`lib/bar_prints.py`, `gcp/fetchers/intraday_bar_flags.py`, `gcp/schema.sql`'s two flag tables). The four unflagged QQQ bars go to a FEAT-DATA-001 issue with their geometry; a rule revision is that capability's.
- No stop floor. Production has no five-minute stop (issue #815; `_traded_exit` uses the brief's structural stop), so a 0.10 ATR floor has nothing to bind on. It ships with the rule change that introduces the signal-side stop, in that spec.
- No ratchet, no day-type filter, no nearest-level first rung, no ORB levels, no brief copy change. Those are the later rule spec.
- No change to the premarket path: `calculate_premarket_context` keeps its own spike rule (#2010, #2046 own the brief's premarket extremes).
- No change to the level builder: triggers, stops, targets and `level_basis` are built from daily bars and the premarket snapshot and are untouched.
- No bar is changed, deleted or replaced in `market_data_intraday` (CLAUDE.md 3.7; the #2001 decision stands).
- No re-resolution of stored rows by this PR. The re-resolve of 2026-09-01 to 2026-11-18 runs after the merge on the owner's yes through the existing `python -m gcp.signal_monitor_eod_resolver --re-resolve` and the resolver's history path; the PR body gives the counts it would change (`done_when` item 9).

## Approaches considered

1. **One shared helper that gives every consumer a touch high and a touch low per bar, computed from the rule itself; the stored bar untouched.** Chosen. One measurement, one lag rule, parity between live, resolver and replay by construction; no new table read on the live path.
2. Read `intraday_bar_flags` in every consumer. Rejected for the live path: the nightly pass writes flags at 21:00 ET, hours after the monitor needed them, and a poll would still need the rule for the newest bars. Kept for nothing: the stored consumers could read the table, but computing from the rule over the same bars gives the same rows (item 1 of #2001's done_when pins it) and needs no second read, no coverage check and no rule-version join. The table stays the audit record; the helper is the consumer contract.
3. Clip the bars at ingestion. Rejected by #2001's owner decision: never replace a value.

## Design

### 1. The helper: `lib.bar_prints.touch_extremes(bars)`, rule `touch-extremes-v1`

One pure function beside `isolated_prints`, in the module that owns the rule. Input: one ticker's regular-session bars of one day, ts ascending, `open`, `high`, `low`, `close`. Output, in input order: `ts`, `touch_high`, `touch_low`, `high_flagged`, `low_flagged`, `judged`.

The stored flags rest on a scale centred on the bar (30 bars each side), which no live consumer can know two bars after the fact (Codex P1 on this PR). So the consumer rule is the stored rule with one change: its scale is **causal**, the median of high minus low over the up-to-61 regular-session bars ending two bars after the bar (fewer at the start of the session). Reference, threshold and flag test are `print_geometry`'s and `isolated_prints`'s. Every consumer feeds the helper the same input, the day's regular-session bars, so the live monitor at 11:30, the resolver that night and a replay next year reach the same decision on the same bar by construction; the two-bar lookahead is the whole of what any of them needs. The rule has its own version, `touch-extremes-v1`, and its own constants, so a change to either rule is a reviewed version bump and never silent.

- `judged` is true when two bars follow the bar in the input.
- For a judged bar, `touch_high` is the stored high, except when the high side is flagged: then it is that side's reference, the highest open or close among the bar and its two neighbours on each side. The low mirrors it. A flagged side therefore contributes, for touch purposes, the highest price that did trade around that minute, not a fabricated one; the stored value is never written.
- An unjudged bar has NaN touch values. The caller decides what to do with it; this helper never guesses (REQ-DATA-001).
- `intraday_bar_flags` stays the audit record under `isolated-print-v1`. The two rules agree wherever volatility is steady and differ around a volatility change; `done_when` item 2 measures the difference on the known sessions and on a changing-volatility fixture, and the PR body publishes it. A consumer records `touch-extremes-v1`, never the stored rule's version.
- Every consumer records `misprint_rule = TOUCH_RULE_VERSION` and `misprints_ignored`, the number of flagged bar-sides inside the window it walked (REQ-DATA-003).

### 2. The live monitor: fold only judged bars

`fetch_latest_bar` returns the last 100 bars a poll. The monitor keeps the snapshot's regular-session bars of the day, runs `touch_extremes` over them, and folds into `_update_session_extremes` and `_advance_leg_state` only the judged bars, using `touch_high` and `touch_low`. The two newest bars of a poll are unjudged and are folded on a later poll, once two bars follow them; the watermark logic at `:707-713` already re-folds from the last folded bar, so the lag needs no new state. Because the scale is causal and bounded by the session start, a bar's decision is the same on the poll that first judges it and on every later poll (item 3 asserts it over three overlapping polls). A snapshot under three regular-session bars folds nothing and logs one line.

Effect: a trigger, target or stop touch is recognised two minutes after the bar that made it, never earlier. The fire path, the indicator window, the ORB and every other reader of the snapshot are unchanged: this spec changes what the leg trackers and the session extremes see, nothing else.

### 3. The playbook resolver and the plan scorer: the same helper over the session

`premarket_playbook_resolver` reads the session's regular-session bars from `market_data_intraday` with two bars of margin after the close, runs `touch_extremes`, and walks `touch_high` and `touch_low` in `resolve_leg`, `_traded_exit` and `resolve_plan`. The tie rule between a stop and a target on one bar is unchanged. `RESOLVER_VERSION` is bumped; a session with no flag resolves byte for byte as before.

`signal_monitor_eod_resolver` is **not** changed. Its exit walk, `_detect_exit`, mirrors `SignalMonitor._check_exits` and compares the bar's close to the target; neither reads a high or a low (Codex P1 on this PR). A flagged close (`print_kind` 'close' or 'open_and_close') is a decision this spec does not take: changing it would change the live exit path too, and `signal_alerts` stays outside this spec with the stop floor and the ratchet.

### 4. Replay

`scripts/replay_signal_monitor.py` and `REPLAY_DATE` hand the monitor the stored bars and the monitor applies Design 2 itself, so a replay of a flagged day equals the live run over the same bars (REQ-REL-001, REQ-REPLAY-001). No replay-only code.

### 5. Schema

`misprint_rule VARCHAR(32)` and `misprints_ignored INTEGER`, nullable, no default, `ADD COLUMN IF NOT EXISTS`, on `premarket_analysis` and `premarket_analysis_history`. A row written before this PR reads NULL, which means not judged, never clean.

### 6. Single source

An AST test holds the three consumer files (monitor, playbook resolver, replay) to the helper: no comparison of a stored high or low against a trigger, target or stop price survives outside it, and the EOD resolver's `_detect_exit` keeps reading no high or low.

### 7. Capacity (CLAUDE.md rule 0)

- Volume: live, one 100-bar snapshot a poll a ticker; stored, one session of about 390 bars plus 14 margin bars.
- Velocity: zero new database reads. The playbook resolver widens its existing read by two bars after the close; the live path reads nothing new.
- Wall-clock: `isolated_prints` is vectorised over the frame; the PR body reports its measured seconds over a 100-bar snapshot and a 390-bar session (item 9); the expectation is milliseconds against a 60-second poll.
- Cost: $0 new. No job, no schedule.

## Risks

- A real flash move that the rule flags is treated as not traded. The rule's own evidence (#2001, Problem 4) flags ten known sessions and a clean sample of none; this spec adds no threshold. The flagged count and the rule version on every row make any such case auditable.
- The two-minute recognition lag on the live path changes when a leg reads triggered. Item 3 pins it; the fire path is unchanged, so no signal fires later than it does today.
- The consumer rule's causal scale differs from the stored rule's centred scale around a volatility change, so a bar can be flagged by one and not the other. Item 2 measures that difference on the known sessions and a changing-volatility fixture and the PR body publishes it; both rules carry their own version on every row they touch.
- Four QQQ bars the rule does not flag stay in the ledgers. Named in Problem, filed under FEAT-DATA-001.
- Re-resolving stored rows changes historical outcome columns. Not done by this PR; the counts are published first (item 9) and the run waits for the owner.
