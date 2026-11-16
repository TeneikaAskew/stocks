---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-004, REQ-DATA-002, REQ-REL-001]
issues: [1076]
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "tests/lib/test_strat_levels.py::TestDailyDataFreshness passes: a session that follows only weekend days and NYSE holidays is fresh when it reads the previous NYSE session (2026-05-26 reading 2026-05-22, 2026-06-22 reading 2026-06-18, 2026-07-06 reading 2026-07-02, 2026-09-08 reading 2026-09-04, 2026-11-27 reading 2026-11-25, Sunday 2026-04-05 reading 2026-04-02 across Good Friday), a frame missing a session is stale (2026-05-26 reading 2026-05-21, 2026-11-27 reading 2026-11-24, Monday 2026-09-14 reading 2026-09-10, Tuesday 2026-09-15 reading 2026-09-11), every expectation that existed on origin/main is unchanged, gap_days stays the calendar-day gap, a gap of 0 or 1 day never consults the calendar, and a calendar failure raises instead of answering fresh or stale; the holiday cases fail on origin/main"
  - "tests/gcp/test_premarket_brief.py passes a test that runs generate_premarket_brief with BRIEF_AS_OF=2026-11-27 on daily bars ending 2026-11-25 and gets a scored ticker (no STALE_DAILY_DATA status, data_freshness_status fresh, a signal_status), and on bars ending 2026-11-24 gets STALE_DAILY_DATA; the first half fails on origin/main"
  - "tests/api/test_movement_statement_router.py passes a test that _build_movement_level_map publishes a ladder for session 2026-05-26 on bars ending 2026-05-22 and refuses it on bars ending 2026-05-21; the first half fails on origin/main"
  - "The PR body shows, for every NYSE session from 2025-01-02 to 2026-12-31 paired with a last bar on each of the ten NYSE sessions before it, that the origin/main rule and the new rule disagree on exactly 21 pairs, each a session reading its previous session (the 21 sessions in this spec's Design), and agree on all other pairs"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-DATA-001, DASHBOARD-01) note row carries that source_identity_sha256"
  - "The FEAT-DATA-001 catalog record and the PR traceability entry are updated, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# The premarket brief's daily-data freshness check counts NYSE sessions

## Authority

The owner approved the fix on 2026-11-11 ("Yes fix the holiday skip and RSI"). This spec is written by a
FEAT-DATA-001 delivery lane and is not self-approved: it takes effect only when the owner merges the
spec-only PR that adds it, and that merge is the approval its `status` records.

## Problem

`lib.strat_levels.daily_data_freshness` (`lib/strat_levels.py:1967-1999` on origin/main 300b40df) is the
one freshness rule for the premarket brief (`gcp/premarket_brief.py:1179`, through
`_resolve_data_freshness` at `:1860-1904`) and the movement-statement ladder
(`platform/api/routers/dashboard.py:493`). It counts calendar days: fresh when the last daily bar is at
most one day before the session, plus two weekend bridges (Monday reading Friday, Sunday reading
Friday). Everything else is `STALE_DAILY_DATA`, and the brief then skips the ticker: no canonical
`premarket_analysis` row, no `strat_levels`, no level_basis for the insight planner, and the
movement-statement endpoint refuses its ladder.

The rule was written before the repo had a calendar the API image could load, and its docstring calls
the holiday false positives deliberate. Since the shared NYSE calendar landed (FEAT-DATA-001,
`docs/superpowers/specs/2026-10-19-feat-data-001-shared-market-calendar.md`, `lib/eastern_time.py`,
and `pandas-market-calendars==5.3.0` in `platform/api/requirements.txt:32`), both images can count
sessions. The cost of the old rule is every session after an NYSE holiday: the brief skipped
2026-05-26, 2026-06-22, 2026-07-06 and 2026-09-08, and the next is Friday 2026-11-27 (it reads
Wednesday 2026-11-25, a two-day gap on a Friday).

The shared-calendar spec listed `strat_levels.daily_data_freshness` semantics as Spec C of the
trading-day standardization. This spec is that slice, for this function only.

## Non-goals

- No other walk-back or freshness rule changes (`_trading_days_between` and
  `persist_level_map`'s `StaleSourceDataError` guard already count sessions; `DataLoader.on_stale`,
  the freshness audit and the playbook resolver are untouched).
- `gap_days` keeps its meaning, the calendar-day gap, because `premarket_analysis.freshness_gap_days`
  stores it and the Discord stale line prints it.
- No change to what a stale ticker does (skip, history row only) or to the stale threshold for a
  genuinely missing session.

## Approaches considered

1. Add each holiday's gap as another exemption. Rejected: a date list, the defect class the shared
   calendar removed (#1076).
2. Chosen: fresh when the last bar is on or after `lib.eastern_time.previous_session(analysis_date)`,
   the last NYSE session strictly before the session the brief is for. Gaps of 0 and 1 day stay fresh
   without a calendar call.
3. Compare session counts with `session_count`. Equivalent; rejected as less direct to read.

## Design

```
gap = (analysis_date - last_bar_date).days
gap <= 1                                   -> fresh (no calendar call)
last_bar_date >= previous_session(analysis_date) -> fresh
otherwise                                  -> STALE_DAILY_DATA
```

`previous_session` raises when the calendar cannot answer (`lib/eastern_time.py`, Rule 3.7), so a
calendar failure is loud, never a fresh or stale guess. The weekend bridges are special cases of the
rule (Friday is the previous session of Saturday, Sunday and Monday), so no exemption list remains.
The docstrings of `daily_data_freshness` and `_resolve_data_freshness`, the dashboard comment and the
`gcp/schema.sql` comment for `data_freshness_status` are updated to the session rule.

Sessions whose previous-session bar the origin/main rule flags and the new rule accepts, 2025-01-02 to
2026-12-31 (pandas-market-calendars NYSE): 2025-01-02, 2025-01-10, 2025-01-21, 2025-02-18, 2025-04-21,
2025-05-27, 2025-06-20, 2025-07-07, 2025-09-02, 2025-11-28, 2025-12-26, 2026-01-02, 2026-01-20,
2026-02-17, 2026-04-06, 2026-05-26, 2026-06-22, 2026-07-06, 2026-09-08, 2026-11-27, 2026-12-28.

## Expected effect

On those sessions the brief scores every ticker and writes its canonical `premarket_analysis` row and
`strat_levels` as on any other morning; the insight planner reads the brief's level_basis instead of
building its own; the movement-statement endpoint publishes its ladder. A session whose previous NYSE
session is missing from the frame is still `STALE_DAILY_DATA`.

## Capacity and cost

- **Volume:** one freshness decision per ticker per brief run (the brief universe, under 20 tickers)
  and one per movement-statement request.
- **Velocity:** no query or network call; `previous_session` reads the process-wide session cache
  built once from pandas-market-calendars (`lib/eastern_time._sessions_covering`), and only when the
  gap is two days or more.
- **Wall-clock:** the first schedule build is the one already paid by other calendar callers in both
  images (recorded in the shared-calendar PR); each later lookup is a bisect, microseconds.
- **Cost:** $0; no new job, schedule or resource.

## Source identity and close-out

`lib/`, `gcp/`, `platform/api` and `tests/` are inside SITE's watched scope (`docs/DOC_REGISTRY.md`,
the row for `docs/product/03-SITE-TRACEABILITY.md`). DASHBOARD-01 (the briefing strip) shows
`premarket_analysis.signal_status`, which the brief now writes on post-holiday sessions. Only the
`(FEAT-DATA-001, DASHBOARD-01)` row of the Implementation-source notes table may describe this
implementation, as backend source and local tests only. Every other SITE byte stays unchanged.

After the merge, separately and never as a pre-merge box: verify main's source and body identity in a
fresh clone, complete the DOC main and staging close-out with real evidence (the `premarket-brief` job
image carries the rule, and the 2026-11-27 brief writes its rows), retire the sidecar as the
product-delivery skill prescribes, and set the plan to `status: done` on a `docs/` branch.

## Risks

- **A provider bar dated on a holiday.** A bar dated on a non-session after the previous session is
  later than the previous session, so it reads fresh, as it does today for a gap of one day.
- **Calendar unavailable.** The brief would raise for any ticker with a gap of two or more days instead
  of skipping it quietly. That is the shared calendar's contract; the API image already ships the
  library.
- **The docs audit reads solyra's issues**; a session without solyra access cannot run it, so the owner
  or a session with that access runs the matched branch and main pair before the PR is marked ready.
