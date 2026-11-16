---
feat_id: FEAT-STRAT-001
req_ids: [REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REPLAY-001, REQ-VALID-001]
issues: [884]
done_when:
  - "The conservative persona's sizing gate in lib/agents/trade_planner.py (both places that read _CONSERVATIVE_MIN_FTFC) no longer reads the direction-blind weighted candle score against +0.30; it stands aside only when 8:30 true FTFC (price vs the quarter, month and week opens, the brief's tf_continuity) is opposed to the trade's direction, and it takes the plan when continuity is aligned, mixed or the brief's explicit unavailable state; lib/agents/summarizers.py summarize_strat_status computes it for the insight pipeline with the brief's own helpers (compute_strat_status with strat.continuity_timeframes_premarket, then timeframe_continuity_record) and returns it as the strat section's tf_continuity, carried through StratSnapshot, so build_context_bundle supplies it with no other source; context_from_bundle carries that continuity from the bundle into PlanContext, a bundle with no recorded continuity makes the conservative plan stand aside with the rationale 'Stand aside: 8:30 continuity not recorded' and a warning log, and any value other than bullish, bearish, mixed or unavailable raises ValueError instead of reading as unavailable"
  - "The conservative stand-aside rationale names the opposed continuity direction instead of the old +0.30 threshold, and the other conservative filters are unchanged: a high-impact catalyst still multiplies the conservative size by _CONSERVATIVE_CATALYST_DAMPER (0.6), and a long below the 200-SMA still stands aside"
  - "The signal monitor does not publish a PDH or PDL break whose crossing bar starts before 09:35 ET, a 09:30 gap open past the level included: no Discord post and no signal_alerts or trades row; it logs the held break with reason opening_5m_hold and counts it per ticker in a run counter; the held (ticker, level, direction) stays consumed for the session, so neither price staying beyond the level through 09:35 nor a later re-cross of it fires, while the opposite direction of that level, every other level and a first crossing at or after 09:35 are evaluated exactly as on origin/main"
  - "Named regression tests, each failing on origin/main: tests/agents/test_conservative_rule3.py drives build_context_bundle on recorded daily bars (the 2026-11-05 brief fixture) with the database and LLM calls captured and no continuity injected into the bundle, asserts its strat section's tf_continuity equals the brief's tf_continuity for the same ticker and session, and carries it through context_from_bundle into compute_persona_plans, so the conservative plan sizes when that reading is aligned or mixed and stands aside when opposed; it also drives compute_persona_plans for long and short on aligned, mixed, opposed and unavailable continuity; drives context_from_bundle on a bundle whose brief continuity is opposed and asserts the built PlanContext carries it and the conservative plan stands aside (so real plans cannot all fall to the unavailable path); asserts, with continuity aligned, that a high-impact catalyst sizes the conservative plan at 0.6 of its normal allocation and that a long below the 200-SMA stands aside; drives context_from_bundle on a bundle with no tf_continuity (the conservative plan stands aside with the not-recorded rationale and a warning is logged) and on bundles whose tf_continuity is 'BULL', 42 and a dict (each raises ValueError); and asserts the rationale names the opposed direction. tests/gcp/test_signal_monitor_opening_hold.py drives the monitor's production fire and persist path with Discord and the database captured, for a first crossing at 09:34 (held), 09:35 (fires) and 09:40 (fires), a 09:30 gap open past PDH (held), price staying beyond a held level through 09:35 (no fire), a re-cross of a held level after 09:35 (no fire), the opposite direction of a held level after 09:35 (fires) and a non-PDH/PDL level at 09:31 (fires as on origin/main)"
  - "A replay of the brief alerts on main vs the branch over 2024-01-02 to 2026-11-04 reproduces this spec's evidence table within 0.02R and 2% of trade count, with the replay command and code hashes in the PR body"
  - "The affected FEAT-STRAT-001 capability and PR traceability records and the spec gate pass; merge and deployed verification are recorded after normal release gates"
status: approved
---

# Conservative persona on "not opposed" continuity, and no breaks before 09:35

## Authority

Proposed on 2026-11-05 by the FEAT-STRAT-001 replay lane. The owner, shown the alert replay results, approved drafting this spec on 2026-11-05. It replaces #1739, re-cut after that PR's second review round found two defects (unreadable continuity read as unavailable, and a catalyst-damper check that contradicted the code); both are fixed here. This file is not self-approved: it takes effect only when the owner authorizes the merge of the PR that adds it, and that merge is the approval its `status` records. It is not a rollout.

## Problem

Two findings from the 2015 to 2026 alert replay (IWM, SPY, QQQ, every trade walked on 1-minute bars, exploration window 2015 to 2023, untouched check window 2024 to 2026):

1. The conservative persona gates on `_CONSERVATIVE_MIN_FTFC = 0.30` against the weighted candle vote, which carries no direction. It passes a short on a bullish score and blocks trades for reasons unrelated to the trade's direction. On the new-code alerts it was the worst of four rules in 2024 to 2026.
2. Prior-day-level breaks in the first 5 minutes (42% to 46% of all breaks, two thirds of them gap opens) are the worst slot of the day in both windows. 09:35 to 09:59 is the best.

## Evidence

Entry at the break, stop at the far side of the prior bar, magnitude target, 5-session hold, R on the underlying, no costs.

| Conservative rule, new-code alerts | 2015-2023 takes | E[R] | win | max DD | 2024-2026 takes | E[R] | win | max DD |
|---|---|---|---|---|---|---|---|---|
| Current main: weighted score at least 0.30 | 292 | +0.03 | 71% | 13R | 104 | -0.15 | 64% | 17R |
| No FTFC minimum | 927 | +0.03 | 65% | 39R | 343 | -0.06 | 63% | 30R |
| 8:30 true FTFC aligned | 25 | +0.22 | 88% | 1R | 2 | n/a | | |
| **8:30 true FTFC not opposed (this spec)** | 543 | +0.06 | 68% | 27R | 193 | -0.05 | 65% | 12R |

| Break timing, all prior-day breaks | 2015-2023 n | E[R] [95% CI] | 2024-2026 n | E[R] |
|---|---|---|---|---|
| 09:30 to 09:34 | 1816 | -0.05 [-0.09, -0.01] | 696 | -0.03 |
| 09:35 to 09:59 | 769 | +0.09 [+0.02, +0.15] | 212 | +0.05 |
| Skip breaks before 09:35, vs taking all (new alerts) | | +0.05 [+0.01, +0.09] | | +0.02 |
| Skip breaks before 09:35, vs taking all (all breaks) | | +0.04 [+0.01, +0.06] | | +0.01 |

Skipping the first 5 minutes was one of two opening-window rules that passed the pre-set test in both windows (difference CI above zero in 2015 to 2023, positive again in 2024 to 2026); it roughly halves drawdown (39R to 21R and 30R to 17R on the new alerts). Close-of-bar confirmation, ORB breakout entries and retests did not pass.

Neither change makes the alerts profitable in 2024 to 2026. They cut losses and drawdown. This spec claims no edge.

## Non-goals

- No new FTFC gate anywhere else. The brief's direction gate, the signal monitor's ORB bonus and FTFC bonus, the high-conviction calibration and the ranker are out of scope (Part B, #1735, owns those).
- No change to stop, target or sizing tables, to the other personas, or to backtests.
- No 5-min ORB alignment rule; it passed only on all breaks, not on the new alerts, and is left as research.

## Approaches considered

1. Keep the 0.30 minimum. Worst rule in the check window and direction-blind.
2. Require 8:30 true FTFC aligned. Leaves 2 takes in three years on the new alerts, because the brief's CALL/PUT score is mean-reversion and rarely coincides with price above all three opens.
3. No minimum. Same as the persona not gating at all; keeps the larger drawdown.
4. Chosen: not opposed. Never worse than no minimum in either window, beats main by 0.10R in 2024 to 2026, cuts check-window drawdown from 30R to 12R.

## Design

- **Persona:** `PlanContext` carries the 8:30 true FTFC direction for the plan's ticker, the brief's `tf_continuity` that #1732 computes and stores, and the insight pipeline's bundle carries it: today `summarize_strat_status` (the strat section of `build_context_bundle`) calls `compute_strat_status` without continuity timeframes and returns no continuity at all, so it gains the brief's computation (`continuity_timeframes_premarket`, then `timeframe_continuity_record`) and a `tf_continuity` field on `StratSnapshot`, and `context_from_bundle` fills `PlanContext` from it. Without that wiring every production plan would take the not-recorded path below. `compute_persona_plans` sets conservative size to 0 only when that direction is opposed to `ctx.direction`. The brief's explicit `unavailable` state (a required open is not known yet, as on the first session of a new week, month or quarter before 09:30) does not block, because that is a legitimate missing value. A failure to read it is not: a bundle with no recorded continuity fails closed (the conservative plan stands aside with "Stand aside: 8:30 continuity not recorded" and a warning is logged), and a value outside bullish, bearish, mixed and unavailable raises `ValueError` from `context_from_bundle` (CLAUDE.md Rule 3.7), so an unreadable reading can never become a nonzero allocation. The catalyst damper (x0.6) and the long-below-200-SMA refusal stay as they are. `_CONSERVATIVE_MIN_FTFC` is removed, and the rationale reads "Stand aside: 8:30 continuity is bearish against a long" (or bullish against a short).
- **Opening hold:** in `gcp/signal_monitor.py`, a PDH or PDL crossing whose bar starts before 09:35 ET is not published: no Discord post, no `signal_alerts` or `trades` row. It is logged with reason `opening_5m_hold` and counted per ticker in a run counter. `check_level_breaks` already consumes its `(ticker, level, direction)` dedup key on the first crossing; the held crossing keeps that key consumed, so the level does not fire later that session in that direction, whether price stays beyond it through 09:35 or crosses back and breaks it again. This is the replay's `skip5` rule (drop a trigger before 09:35). Entering at 09:35 when price is still beyond the level (`delay5`) was tested and did not pass, so it is not what this spec approves. The opposite direction, other levels, and first crossings from 09:35 behave as on origin/main.

## Capacity and cost

- **Volume and velocity:** no new queries. The persona reads a field already computed for the brief; the monitor compares a bar timestamp it already has.
- **Wall-clock:** unchanged.
- **Cost:** $0 new GCP workload, schedule or resource.

## Risks

- **Fewer conservative takes on strong trend days** where continuity is opposed early. Measured above.
- **A held 09:30 to 09:34 break never re-qualifies** that session in its direction, even if price runs away or re-crosses later; those are the trades the replay says lose on average.
- **Briefs with no recorded continuity** (rows from before #1732 deployed) make the conservative persona stand aside rather than take; this is the safe direction for that persona and ends once every brief records it.
- **Minute data:** the evidence uses Alpha Vantage 1-minute bars, not the repo's Cloud SQL tables; the done_when replay re-checks it.

## Validation and rollout

1. This spec-only change, on branch `docs/spec-feat-strat-001-persona-rule3-open-skip`, holds this file only.
2. It passes `python3 scripts/gate/spec_gate.py --pr origin/main` and normal review, and merges only on owner authorization.
3. A plan and implementation PR follow under this spec, after #1735.
4. No production action from this PR.

Research files: strat-verify/alert-replay/REPORT.md and tables.md (project files), with the scripts that produced them.
