---
feat_id: FEAT-IND-001
req_ids: [REQ-DATA-002, REQ-REL-001, REQ-PLAYBOOK-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "tests/lib/test_brief_level_breaks.py passes: add_brief_indicators produces Broke_Prev_Day_High and Broke_Prev_Day_Low equal to calculate_historical_levels' definition (a session's close above the previous session's high, below its low), changing or appending later bars leaves every earlier flag unchanged, and a brief row can score 5 of 5 on CALL and on PUT; the tests fail on origin/main"
  - "add_all_indicators and add_signal_indicators are unchanged: tests/lib/test_indicators.py passes, including the pinned add_all_indicators column set and the signal and brief tier parity"
  - "The PR body shows the old and new brief CALL/PUT status for IWM, SPY and QQQ on the 20 sessions through 2026-11-04 and the 2026-11-05 brief, and the count of changed days from 2015-01-02"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-IND-001, DASHBOARD-01) note row carries that source_identity_sha256"
  - "The FEAT-IND-001 catalog record and the PR traceability entry are updated, the matched current-main-versus-branch docs_audit.py run reports nothing new, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# The premarket brief's level-break conditions: produce Broke_Prev_Day_High and Broke_Prev_Day_Low

## Authority

Proposed on 2026-11-05 by a FEAT-IND-001 delivery lane, from the read-only FTFC replay of IWM, SPY and
QQQ daily bars (2015 to 2026) that the owner asked for on 2026-11-05. It is not self-approved: it takes
effect only when the owner authorizes the merge of the spec-only PR that adds it, and that merge is the
approval its `status` records.

## Problem

`check_call_conditions` and `check_put_conditions` (`lib/signals.py:88-93`, `:154-158`) score a fifth
condition, `level_break_pdh` / `level_break_pdl`, from `Broke_Prev_Day_High` / `Broke_Prev_Day_Low`,
read with `row.get(..., 0)`. The premarket brief (`gcp/premarket_brief.py:1129-1131`, `:1249-1250`)
scores the row returned by `add_brief_indicators` (`lib/indicators.py:1540-1569`), which does not produce
those columns, and its SQL frame (`lib/data_loader.py:517-540`) does not select them. So the factor
never scores and the brief's CALL and PUT scores top out at 4 of 5. The intended definition already
exists twice: `calculate_historical_levels` (`lib/indicators.py:505-507`, close above the previous
session's high, below its low) and `lib/trading_analysis.py:483-484`.

## Non-goals

- No change to `add_all_indicators`, `add_signal_indicators`, `FEATURE_GROUPS` or the stored
  `market_data_daily` schema; the live signal monitor's intraday path is not changed.
- No change to `check_call_conditions` / `check_put_conditions`, the brief's thresholds (setup 3,
  building 2) or the FTFC gate in `_resolve_signal_status`.
- `lib/data_loader.py` and `gcp/premarket_brief.py` are not edited.

## Approaches considered

1. Add the columns to the brief's SQL select. Rejected: `market_data_daily` has no such columns, and a
   stored flag would be a second copy of a value the brief can derive from the bars it already holds.
2. Add the block to `add_all_indicators`. Rejected: it changes the pinned full-engine column set and
   every path that reads it.
3. Chosen: a brief-only block, `_add_prev_session_level_breaks`, run last in `add_brief_indicators`,
   that takes the two flags from `calculate_historical_levels` on the frame's own sessions (the `Time`
   column, else a `DatetimeIndex`; a frame with neither gets no flags, like the VWAP and ORB blocks).

## Design

The brief keeps bars dated before the analysis date and drops null-close rows before it calls
`add_brief_indicators`, then scores the last row, the last completed session D. On that row the flags
compare D's close with session D-1's high and low. Each row reads only its own session and the one
before it, so a replay cut at a date sees the flags the brief saw live (REQ-DATA-002), and the first
session in a frame has no break.

## Expected effect

The brief's CALL and PUT scores can reach 5 of 5, and a day whose close broke the prior session's high
(low) gains a point on CALL (PUT). The published status moves between No signal, building and setup only
where that point crosses a threshold. The PR body carries the per-day evidence.

## Capacity and cost

- **Volume and velocity:** one `calculate_historical_levels` pass per ticker per brief run over the
  frame the brief already loads (about 2,500 daily rows per ticker); no new query or call.
- **Wall-clock:** milliseconds per ticker.
- **Cost:** $0 new GCP workload, schedule or resource.

## Source identity and close-out

`lib/` and `tests/` are inside SITE's watched scope (`docs/DOC_REGISTRY.md`, the row for
`docs/product/03-SITE-TRACEABILITY.md`). DASHBOARD-01 (the briefing strip) shows
`premarket_analysis.signal_status`, which the `premarket-brief` job writes from these scores, and names
`lib/indicators.py` in its Backend cell. Only the `(FEAT-IND-001, DASHBOARD-01)` row of the
Implementation-source notes table may describe this implementation, as backend source and local tests
only, with no claim of deployment or review. Every other SITE byte stays unchanged.

After the merge, separately and never as a pre-merge box: verify main's source and body identity in a
fresh clone, complete the DOC main and staging close-out with real evidence (the `premarket-brief` job
image carries the block), retire the sidecar as the product-delivery skill prescribes, and set the plan
to `status: done` on a `docs/` branch.

## Risks

- **More setup days.** Every break adds a point, so some days move from building to setup. done_when 3
  shows the count.
- **Adjusted versus stored bars.** The evidence replays split- and dividend-adjusted bars; production
  reads `market_data_daily`. A break within a dividend's size of the prior high or low could differ.
- **The docs audit reads solyra's issues**; a session without solyra access cannot run it, so the owner
  or a session with that access runs the matched pair before the PR is marked ready.
