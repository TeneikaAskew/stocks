---
feat_id: FEAT-STRAT-001
req_ids: [REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REPLAY-001, REQ-VALID-001]
issues: [866]
done_when:
  - "The conservative persona's sizing gate in lib/agents/trade_planner.py no longer reads the direction-blind weighted candle score against +0.30; it stands aside only when 8:30 true FTFC (price vs the quarter, month and week opens, calculate_timeframe_continuity) is opposed to the trade's direction, and it takes the plan when continuity is aligned, mixed or unavailable"
  - "The conservative stand-aside rationale names the opposed continuity direction instead of the old +0.30 threshold, and the other conservative filters (catalyst damper, long below the 200-SMA) are unchanged"
  - "The signal monitor does not publish a prior-day-level break that triggers before 09:35 ET; a break first seen from 09:30 to 09:34 is recorded as held with its reason, and a later break of the same level after 09:35 is evaluated as usual"
  - "Focused tests cover rule 3 on aligned, mixed, opposed and unavailable continuity for long and short, and cover the 09:35 hold at 09:34, 09:35 and after, including a gap open past the level"
  - "A replay of the brief alerts on main vs the branch over 2024-01-02 to 2026-11-04 reproduces this spec's evidence table within 0.02R and 2% of trade count, with the replay command and code hashes in the PR body"
  - "The affected FEAT-STRAT-001 capability and PR traceability records and the spec gate pass; merge and deployed verification are recorded after normal release gates"
status: approved
---

# Conservative persona on "not opposed" continuity, and no breaks before 09:35

## Authority

Proposed on 2026-11-05 by the FEAT-STRAT-001 replay lane. The owner, shown the alert replay results, approved drafting this spec on 2026-11-05. This file is not self-approved: it takes effect only when the owner authorizes the merge of the PR that adds it, and that merge is the approval its `status` records. It is not a rollout.

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

- **Persona:** `PlanContext` carries the 8:30 true FTFC direction for the plan's ticker (Part B's live continuity field, #1735; if that PR has not merged, this change adds the field from `calculate_timeframe_continuity`). `compute_persona_plans` sets conservative size to 0 only when that direction is opposed to `ctx.direction`. Unavailable continuity (first session of a new week, month or quarter before 09:30) does not block. `_CONSERVATIVE_MIN_FTFC` is removed, and the rationale reads "Stand aside: 8:30 continuity is bearish against a long" (or bullish against a short).
- **Opening hold:** in `gcp/signal_monitor.py`, a level-break fire whose first qualifying 1-minute bar starts before 09:35 ET is not published. It is logged and stored as held with reason `opening_5m_hold`. From 09:35 the monitor evaluates the level as usual, so a break still beyond the level then fires on the next qualifying bar.

## Capacity and cost

- **Volume and velocity:** no new queries. The persona reads a field already computed for the brief; the monitor compares a bar timestamp it already has.
- **Wall-clock:** unchanged.
- **Cost:** $0 new GCP workload, schedule or resource.

## Risks

- **Fewer conservative takes on strong trend days** where continuity is opposed early. Measured above.
- **A held 09:30 to 09:34 break never re-qualifies** if price runs away; those are the trades the replay says lose on average.
- **Minute data:** the evidence uses Alpha Vantage 1-minute bars, not the repo's Cloud SQL tables; the done_when replay re-checks it.

## Validation and rollout

1. This spec-only change, on branch `docs/spec-feat-strat-001-persona-rule3-open-skip`, holds this file only.
2. It passes `python3 scripts/gate/spec_gate.py --pr origin/main` and normal review, and merges only on owner authorization.
3. A plan and implementation PR follow under this spec, after #1735.
4. No production action from this PR.

Research files: strat-verify/alert-replay/REPORT.md and tables.md (project files), with the scripts that produced them.
