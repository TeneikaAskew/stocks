---
feat_id: FEAT-STRAT-001
req_ids: [REQ-SIGNAL-001, REQ-REL-001, REQ-DATA-001, REQ-PLAYBOOK-001]
issues: []
canvases: []
site_source_notes: [INSIGHTS-04, INSIGHTS-07, SIGNALS-04]
done_when:
  - "Ranker setup points work: gcp/fetchers/fetch_market_data.py and gcp/backfill_ticker.py read the in-force combo from the strat_combo column that StratClassifier.detect_combos returns (today they read a 'combo' key that never exists, so strat_combo is never written by those paths and strat_setup is always False), treat the 'none' sentinel as no combo, and set strat_setup from the combo alone with no |ftfc_score| >= 0.3 test; a test drives the real writer function on daily bars whose last bar completes a 2-1-2 and asserts strat_combo and strat_setup True, and the test fails on origin/main"
  - "lib/agents/ranker/signals.py signal_strat_alignment scores only the setup part (0.34 when strat_setup is true, else 0) and no longer adds points from ftfc_score or ftfc_direction; raw still carries strat_setup, ftfc_score, ftfc_direction and strat_combo; a test with a stored inside-bar day (ftfc_direction mixed) and a stored 2U day with the same strat_setup gives the same score, and fails on origin/main and on the FEAT-INSIGHT-001 consumer-gates branch"
  - "Each signal-monitor fire records, in a new nullable signal_alerts.fire_context JSONB column added in gcp/schema.sql, the live price-open continuity at fire time (lib.strat.calculate_timeframe_continuity over Q, M, W and D at the fire price, with the period opens from the brief's tf_continuity_frames and, for a period that opens that session, the session's first regular-hours open; unavailable when an open is missing) and, for IWM, SPY and QQQ, which of the three have traded through the prior session's high (for a CALL) or low (for a PUT) by the fire's bar time; the fire still persists when the column is absent"
  - "Fire decisions and scores are unchanged: on the existing signal-monitor replay fixtures, strat_bonus, total_score, strength_label, position_size, Discord delivery and the brief tag of every fire are byte-identical to origin/main; no gate, score or threshold reads fire_context"
  - "The fire's Discord embed adds one line with the live continuity state and its frames (for example 'FTFC at fire: bullish (Q M W D green)' or 'FTFC at fire: unavailable'), and the existing 'Strat bonus' line is unchanged"
  - "PersonaPlan risk_metrics gains continuity_aligned (Optional[bool]): True when the brief's 8:30 tf_continuity direction matches the trade direction, False when it is the other direction or mixed, None when the brief recorded no reading; ftfc_aligned, _calibrate_conviction and the conservative persona's minimum read exactly what they read on the FEAT-INSIGHT-001 consumer-gates branch, and tests/agents/test_ftfc_consumer_gates.py passes unchanged"
  - "Unchanged by this spec, each pinned by an existing or added test: gcp/premarket_brief.py _resolve_signal_status (brief CALL/PUT side pick), lib/strategies/brief_bias.py classify, StratClassifier.get_strat_bonus and StratConfig values, the orchestrator's high-conviction rule, the conservative persona minimum, lib/backtest.py's FTFC filter and bonus, lib/exec_backtest/runner.py v1_ftfc, scripts/run_walk_forward.py defaults, and the TF bias score, labels and columns"
  - "The implementation PR body shows, for IWM, SPY and QQQ from 2015-01-02 to 2026-11-04, the changed-day counts in this spec's Expected effect table recomputed on the implementation head, and the before and after decision for the 20 sessions through 2026-11-04"
  - "Source identity (INSIGHTS-04, INSIGHTS-07, SIGNALS-04): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, INSIGHTS-04 / INSIGHTS-07 / SIGNALS-04) note rows carry that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 and FEAT-INSIGHT-001 catalog records, the SIGNAL docs for fire_context and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the fire_context production column apply is recorded separately after the owner's yes"
status: approved
supersedes: null
---

# Where TF bias is used, where true FTFC is shown, and the ranker's Strat setup points

## Authority

Proposed on 2026-11-05 by the STRAT delivery lane after the owner agreed to a spec for "Part B" of
the FTFC work (stop using TF bias as a Strat setup gate, show true FTFC live as context, record
cross-ticker agreement for research). It is not self-approved: it takes effect only when the owner
authorizes the merge of the spec-only PR that adds it, and that merge is the approval its `status`
records. It depends on the FEAT-STRAT-001 continuity spec and code (#1729, #1732: tf_continuity and
tf_continuity_frames) and on the FEAT-INSIGHT-001 consumer-gates spec and code (#1730, #1733), and
opens no implementation PR until those are on main.

Two questions in this spec are the owner's and are not defaulted here (Open questions).

## Problem

TF bias is the weighted candle vote (`StratClassifier.calculate_ftfc`, weights 1d 0.30, 1w 0.10,
1mo 0). Its direction is the prior session's daily candle on every day replayed. The setup replay
(strat-verify/setup-replay/REPORT.md) showed that, used as an "aligned" gate on daily Strat setups,
it would block every 2-2 reversal and every inside-bar setup, because the setup bar is that candle.

Reading every consumer in the code at origin/main 5ce0ad17 shows that no live path actually gates
daily Strat setup triggers on TF bias. The signal monitor scores intraday fires (its combo is
detected on the monitor's own intraday frame), the brief scores a 5-point mean-reversion checklist,
and the insight pipeline gates an LLM-chosen direction. The one live place where the vote decides
whether a daily Strat setup counts is the ranker, and there the setup points never fire at all:

1. `gcp/fetchers/fetch_market_data.py:383-390` and `gcp/backfill_ticker.py:463-465` read
   `detect_combos(...).iloc[-1].get('combo')`. `detect_combos` returns `strat_combo`
   (checked on SPY daily bars), so `last_combo` is always None, `strat_combo` is not written by
   these paths and `strat_setup` is always False. The ranker's `strat_alignment` (weight 3.0, "the
   Strat is the primary signal") has given 0 setup points to every ticker.
2. With that fixed, the writer would also require `|vote| >= 0.3`, which drops 95 of 7,380
   combo-days (inside compressions, 1-3-1 and some 2-1-2 and 3-1-2 reversals).
3. The FEAT-INSIGHT-001 fix (#1733) turns on the ranker's direction points, +0.33 whenever the vote
   is bullish or bearish. The vote is mixed on exactly the 927 days whose prior bar is an inside bar,
   which is the setup bar of a 2-1-2 or 3-1-2. So that fix scores a ticker about 1 ranker point
   (0.33 x 3.0) lower precisely when it is sitting on an inside bar.

Separately, true FTFC (price against the period opens) is now computed premarket (#1732) but is not
shown or recorded at the moment a live signal fires, and cross-ticker agreement, the one feature
that held in both replay windows, is not recorded anywhere.

## How each place uses TF bias today

| Place | File | Rule today | Inside-bar day (TF bias mixed) today |
|---|---|---|---|
| Brief CALL/PUT side pick | gcp/premarket_brief.py:1850-1901 | Forced side: bullish shows CALL only, bearish PUT only, mixed picks the higher score | Not blocked: free pick |
| Signal monitor bonus | lib/strat.py:546-592, gcp/signal_monitor.py:1278-1309 | Aligned +1, opposed -1, at abs(score) >= 0.6; else 0 | 0, no penalty |
| Planner ftfc_aligned flag | lib/agents/trade_planner.py:663-667 | Aligned at 0.5 in the trade's direction | Never aligned |
| Orchestrator high conviction | lib/agents/orchestrator.py:883-937 | Requires aligned at 0.5 | High conviction impossible |
| Conservative persona minimum | lib/agents/trade_planner.py:572-577 | main: score >= +0.30 for either side; #1733: aligned at 0.30 | Stands aside both ways |
| Ranker strat_alignment | lib/agents/ranker/signals.py:45-91 + the writers above | Setup gate abs(vote) >= 0.3 (dead, see Problem 1); magnitude points bullish only; direction points (dead on main, on with #1733) | 0 direction points with #1733 |
| Backtest and walk-forward | lib/backtest.py:791-835, scripts/run_walk_forward.py | Not-opposed filter at 0.6 plus the bonus, on the backtest's own 7-frame intraday vote, not TF bias | Passes |

Also reading the vote: the strat analyst prompt (lib/agents/prompts.py:42-47, "Bias follows from FTFC
direction unless the strat combo contradicts it") and `lib/strategies/gamma_proximity.py`
(prior-day direction, research only via gcp/research/p2_outcomes_grid.py). Neither is changed here
(Non-goals).

## Expected effect if TF bias were removed at each place (replay)

IWM, SPY and QQQ, decision days 2015-01-02 to 2026-11-04, 8,934 ticker-days, each decision made by
the repo's own functions on the Part A code (#1733 and #1734 applied), as in the bug-fix evidence.
Scripts and tables are in the lane's research folder strat-verify/partb-replay/ (outside this repository).

| Place | What flips if TF bias is removed | Outcome on the flipped days | This spec |
|---|---|---|---|
| Brief side pick | Status text on 4,119 days (46%). Setup days 1,879 to 4,326: 797 CALL and 1,650 PUT setups added, none removed, all on the side the gate hides | The side shown instead was right 49.1% (2015-2023) and 52.0% (2024-2026) open to close; the hidden side it replaces 50.9% and 48.0%; base rate 53.2% and 51.1% | Keep |
| Monitor bonus | The FTFC term is nonzero on 5,582 days (62%): a CALL gets +1 on 3,366 and -1 on 2,216, a PUT the mirror | Fire-level tiers need signal_alerts (query below); the earlier FTFC replay found the bonus days within noise | Keep the score; record live FTFC beside it |
| Planner flag | Swapping to 8:30 true FTFC: long True to False 1,272, False to True 830; short 1,655 and 389; no reading on 2,091 days (new week, month or quarter) | Within noise in the FTFC replay | Keep; add continuity_aligned beside it |
| High conviction | Dropping the FTFC condition: long high 4,032 to 8,934, short 3,118 to 8,934 (on otherwise qualifying days); reading true FTFC instead: 2,658 and 1,117 | Within noise | Keep |
| Conservative persona | See Open question 1 | No difference in the FTFC replay | Owner's choice |
| Ranker | Score changes on 7,861 days versus #1733; mean 0.395 to 0.281; setup points on 0 days today, 7,380 (83%) after | Neither vote version's points helped in the FTFC replay | Change |
| Backtest, walk-forward | Not replayable here: needs the 5-minute bars in Cloud SQL | Existing walk-forward runs with the filter off can be read (query below) | Keep |

An earlier estimate of 2,700 to 3,550 more Strat triggers came from the setup replay's
hypothetical aligned gate. No live path applies that gate, so removing TF bias does not add those
triggers anywhere. The only live Strat setup change is the ranker's.

## Non-goals

- No change to the brief's CALL/PUT side pick, brief_bias, the bonus, StratConfig, the TF bias
  score or columns, the conservative persona minimum, high conviction or any backtest. The evidence
  shows no edge for removing TF bias at those places, and removing it at the brief would more than
  double the setups shown at coin-flip quality.
- No gate on true FTFC or on cross-ticker agreement: both are recorded and shown only.
- The strat analyst prompt is not reworded: its effect can't be measured without re-running the
  LLM. Proposed as a follow-up.
- No change to solyra; the dashboard API exposes nothing new in this spec.
- No target or stop change (see Risks).

## Approaches considered

1. Remove TF bias from every decision place (the first outline). Rejected: at the brief, bonus,
   planner and conviction it is not a Strat setup gate, removing it moves thousands of decisions,
   and no replay showed the moved decisions were better.
2. Replace TF bias with true FTFC at every place. Rejected: the FTFC replay found no difference, and
   true FTFC is unavailable at 8:30 on 23% of days.
3. Chosen: change only the place where the vote decides whether a Strat setup counts (the ranker),
   fix the writer bug that hides setups from it, and record true FTFC and cross-ticker agreement at
   the fire so a later decision on the bonus rests on real fires.

## Design

1. Writers (fetch_market_data.py, backfill_ticker.py): `last_combo = combos['strat_combo'].iloc[-1]`,
   None when 'none' or null; `strat_setup = bool(last_combo)`. strat_candle, ftfc_score and
   ftfc_direction are written as today.
2. Ranker: `score = setup_pts` (0.34 or 0). The 0.66 previously reserved for the vote is not
   reassigned; a follow-up may score pending setups (detect_combos `pending_setup`) once tested.
3. Monitor: build `fire_context = {'ftfc_live': {state, frames}, 'cross_ticker': {ticker: bool,
   'same_direction_n': int}}` after scoring and before persist, from data the monitor already holds
   (brief row, session bars of IWM, SPY and QQQ). Failure to build it leaves it null and logs once
   per ticker per session. Persist adds the column to the upsert only when the column exists.
4. Planner: `continuity_aligned` from the brief's `tf_continuity` passed through the strat snapshot;
   the reviewer prompt shows it as information (no rule reads it).
5. Display: the fire embed line in Design 3; the insight Discord embed shows the plan's
   continuity_aligned beside the existing FTFC line.

Consumers touched: 2 writers, 1 ranker signal, the monitor persist and embed, the planner schema and
prompt text, gcp/schema.sql. Tables: market_data_daily strat_combo and strat_setup start being
written (no new columns there); signal_alerts gains fire_context (nullable JSONB); insight_reports
JSONB carries continuity_aligned. Jobs to redeploy: fetch-market-data, backfill-ticker,
auto-refresh-top-n and insight-pipeline (and the API image that serves insights), signal-monitor and
signal-replay, insight-discord-push. premarket-brief, backtest, backtest-pipeline and param-sweep are
unchanged.

## Open questions for the owner

1. Conservative persona, once TF bias is no longer the trend input (takes per 8,934 days, synthetic
   context, other persona rules fixed):

   | Option | Long takes | Short takes |
   |---|---|---|
   | Keep the #1733 rule on TF bias (no change) | 4,032 | 3,118 |
   | A: no FTFC minimum | 8,934 | 8,934 |
   | B: 8:30 true FTFC in the trade's direction | 2,658 | 1,117 |
   | C: 8:30 true FTFC not against the trade | 7,817 | 6,276 |

   This spec keeps the current rule until the owner picks; a different pick is a one-line follow-up
   spec.
2. The ranker part of #1733 (direction points) is replaced by this spec. Keeping it in #1733 means
   the ranker scores inside-bar tickers about 1 point lower until this spec's code lands. Dropping it
   means re-cutting #1730 and #1733 without that item (both are past their second review round, so
   the repository's review cap requires new PRs), which delays the conservative-short and rounding
   fixes by one review cycle.

## Queries this spec could not run (Cloud SQL is not reachable from the lane)

- strat-verify/partb-replay/gcp_request/market_data_daily_strat_setup.sql: confirms strat_setup is
  never true in production.
- .../monitor_bonus_tiers.sql: fires whose strength tier and Discord delivery would change without
  the FTFC term.
- .../walk_forward_ftfc_filter.sql: existing walk-forward folds with the filter on ('strat') and off
  ('s_noftfc').

## Risks

- More setups at about break-even: once the writer bug is fixed, the ranker gives setup points on
  83% of days, and the setup replay put daily setups at -0.20R to +0.02R. Ranker setup points are a
  ranking input, not a trade; a target and stop study (the magnitude target sits a median 0.5R
  away) should come before any setup becomes a trade trigger.
- The ranker's strat_alignment mean moves from 0.395 (with #1733) to 0.281 and stops reacting to
  direction; top-N membership can change. The implementation PR shows the before and after scores.
- fire_context adds work to every fire; the build reuses frames the monitor holds and must not delay
  the alert (done_when 4 pins the fire outputs).
- A production schema apply is needed for fire_context; the code tolerates the column's absence.
