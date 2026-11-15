---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-VALID-001, REQ-CAP-001, REQ-CAP-002]
issues: [815]
canvases: []
site_source_notes: [DASHBOARD-05]
done_when:
  - "tests/scripts/test_run_historical_signals_plan.py::test_attach_query_shape passes: for one ticker with N signals over K sessions (N 2,500, K 20) the attach step issues exactly 5 read queries and ceil(N / 1000) writes; the 5 reads are the bars for the window, the stored signals' keys, the daily rows with their premarket fields, the parameters in force over the range (one query of the range read beside load_level_params) and the open basis over the range (one query of the range form of read_open_level_basis)"
  - "tests/scripts/test_run_historical_signals_plan.py::test_attach_plans passes: --attach-plans --start-date D updates plan and outcome columns of stored rows from D on, changes no other column and no row before D, never deletes, and a second run changes nothing; a stored row whose entry_time has no bar in the frame, or whose entry_price differs from that bar's close by more than half a cent, gets plan_status bar_mismatch and NULL plan prices; a stored row on its session's last regular-hours bar gets plan_r_status no_fill with plan_fill_price and plan_r NULL; --attach-plans with --dry-run writes nothing"
  - "tests/gcp/test_signal_plan_level_source.py::TestOpenBasisAttach passes: for a session with an early live brief write at 08:30, a late write at 09:22 and the canonical live row overwritten at 10:32, --attach-plans gives that session's stored signals at 09:35 and 14:00 plan_status basis_replaced with every plan price NULL, never the 10:32 levels and never a rebuild"
  - "Source identity (DASHBOARD-05): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-SIGNAL-001, DASHBOARD-05) note row carries that source_identity_sha256"
  - "The FEAT-SIGNAL-001 catalog record (Status, Last reviewed) and the PR traceability entry are updated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
  - "The PR body carries the Capacity section of this spec with the attach run's measured numbers from a --dry-run on one ticker (signals, read queries, seconds per stage), next to the estimates"
status: approved
supersedes: null
---

# Signals carry their plan, history attach: plans and R outcomes for the stored signals of SPY, QQQ and IWM, by update

## Authority and status

The content of this spec was approved by the owner (T) on 2026-11-14 as part of the parent spec,
`docs/superpowers/specs/2026-11-14-feat-signal-001-signals-carry-their-plan.md`, with: "Im fine with
signal plan." That approval took the parent's decision 6 (History), which this spec carries out.

On 2026-11-15 the owner answered the recommendation "split it" for PR #1950 with: "Yes do whats needed
to be completed". The parent records that as its decision 8: the range parameter read, `--attach-plans`
and the dry-run measurement move here. No code is written under this spec before it, and the parent's
implementation, are on main.

The text below is moved from the parent, verbatim where it could be. "Decision N" and "Design N" name
the parent's sections. Every statement about code or data keeps the parent's mark, "read" (read in the
source, not executed) or "run" (executed; the execution name is in "Queries run"), and code references
are to origin/main at 515f8fde, as in the parent.

What changed in the move, so a reviewer can check it against the parent:

- The attach half of the parent's `test_query_shape` is `test_attach_query_shape` here. Its five reads
  are named from the parent's Design 5.
- The attach case of the parent's `TestOpenBasis` is `TestOpenBasisAttach` here.
- `test_attach_plans` gains the last-bar case (`no_fill`, the parent's decision 8 and Design 4),
  because the attach writes the outcome columns through the same scoring.
- The source identity and product-record items are added. An implementation PR cannot add its own
  `site_source_notes` declaration, and the attach changes `lib/` and `scripts/`, which SITE watches.
- No canvas is listed. The attach changes no row of `docs/product/07-MODEL-REGISTRY.md`, so the models
  diagram the parent lists does not change.

## Depends on

The parent spec is implemented first, and its implementation is on main before this spec's branch is
cut. This spec uses, and does not change:

- the plan and outcome columns on `historical_signals` (the parent's Design 3 and Design 4);
- `lib/signal_plan.py`: `build_signal_plan` and `score_signal_plan` (Design 2), with the `no_fill`
  outcome for a signal on the session's last regular-hours bar (Design 4);
- `lib.strat_levels.read_open_level_basis` and its range form (Design 2);
- the history step in `scripts/run_historical_signals.py::_process_ticker` (Design 2).

It adds the range parameter read and `--attach-plans`, and measures the run.

## Capability

FEAT-SIGNAL-001, as in the parent. Its row in `docs/product/02-FEATURE-CATALOG.md` (line 21):

> | [FEAT-SIGNAL-001](#feat-signal-001) | Signals / execution | Signal discovery, alerting, exits | `/signals`, `/live` | `/api/signals` | `signal_alerts`, `historical_signals`, `exit_config_overrides` | Production but needs remediation | P0 | 1 | 25 | [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#928](https://github.com/TeneikaAskew/stocks/issues/928) [#1206](https://github.com/TeneikaAskew/stocks/issues/1206) |

## Problem

From the parent: "A stored signal is a time, a direction and a price. It has no stop and, in history,
no target, so it cannot be scored in R, and every evaluation so far had to invent the plan afterwards."
The three signal tables hold no column named like stop, plan, t1 or target except
`signal_alerts.target_price` and `time_stop_minutes` (run, db-query-t4nsl).

The parent gives a plan to every row the generator inserts from its deploy on, and its pending pass
selects only rows with `plan_version` set (the parent's Design 4). Rows stored before the deploy keep
`plan_version` NULL and no plan. This spec gives the stored signals of SPY, QQQ and IWM from 2025-03-03
their plan and outcome.

The decision it carries out, the parent's decision 6, verbatim:

> 6. **History.** **Decided: plans are attached to the stored signals of SPY, QQQ and IWM from
>    2025-03-03 by update, with no delete and no regeneration; live alerts get plans from the deploy on
>    and are not backfilled.**
>    - A plan is a function of the signal's bar, its direction and the session's levels. The signals
>      themselves do not change, so nothing needs regenerating a second time once the runbook's
>      regeneration of `historical_signals` on the clean bars has run. Before that it must not run: most
>      stored signals of 2026-04 to 2026-09 carry Eastern-label times, and in 09:30 to 15:34 only 5% to
>      35% of them coincide with a regenerated signal (`clean-set/STATUS.md`, 18:49Z). As a guard, a
>      stored row whose entry_time has no bar, or whose entry_price is not that bar's close, gets
>      `plan_status` `bar_mismatch` and no plan.
>    - The only regeneration path that exists is `--force`, which deletes every row of the ticker and
>      strategy before it generates and commits that delete first (`gcp/historical_signals.py:118-137`
>      and `scripts/run_historical_signals.py:453-460`, read; hazards 1 and 2 of the recompute spec). An
>      update in chunks cannot leave a ticker empty.
>    - 2025-03-03 is the window already measured: 293 sessions before 2026-05-01 and 137 after, 43,573,
>      44,000 and 39,025 momentum signals (`clean-set/STATUS.md`, 18:45Z).
>    - **A plan needs the ticker's level parameters in force on the session, and production has none
>      before 2026-11-12** (run, db-query-8ptk7: `ticker_level_params` holds 23 `on_demand` rows per
>      ticker, all effective 2026-11-12; SPY has 19 of 23 ok). Until the history-mode calibration of
>      FEAT-STRAT-001 is written for the window, every stored signal before 2026-11-12 would get
>      `params_unavailable`. So the attach waits until that calibration is written for the window, which
>      is FEAT-STRAT-001's step and needs the owner's yes of its own. The local evaluation used its own
>      local calibration.
>    - Stored live alerts (3,146 live rows, run, db-query-t4nsl) keep NULL plans. A replay with
>      `REPLAY_DATE` writes `run_kind='replay'` rows with plans for any date whose parameters exist.

Full paths of the evidence files, all under
`/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/`:
`clean-set/STATUS.md`. It is a session file, not in the repo.

## Non-goals (what does not change)

- No regeneration and no delete. No change to `scripts/run_historical_signals.py --force` (decision 6
  and the parent's Non-goals).
- Stored live alerts in `signal_alerts` are not backfilled; they keep NULL plans (decision 6).
- Which bars fire a signal, the plan builder, the leg walk, the columns, the open-basis reader and the
  generator's pending pass: they are the parent's, and this spec calls them unchanged.
- No column of a stored row other than its plan and outcome columns changes.
- No figure includes a trading cost.

## Approaches considered

1. **Regenerate `historical_signals` with `--force`.** Rejected (decision 6): it deletes every row of
   the ticker and strategy before it generates and commits that delete first, and over the full stored
   history it takes about 68 minutes a ticker (estimate, local speed), over the 1,800 s task timeout
   (Capacity).
2. **Update the stored rows in keyed chunks through the parent's history step (chosen).** An update in
   chunks cannot leave a ticker empty, and a rerun converges because the update is keyed and
   idempotent.

## Design

### 1. What `--attach-plans` does

`scripts/run_historical_signals.py --attach-plans --start-date D` is the path that rebuilds plan and
outcome over a chosen window. It runs the parent's history step, the one the generator runs in
`_process_ticker` after the signals frame exists and before `map_signals_to_table`, for both strategies
(Design 2), over the stored rows of one ticker from D on.

- It updates the plan and outcome columns of stored rows from D on, changes no other column and no row
  before D, never deletes, and a second run changes nothing. With `--dry-run` it writes nothing.
- A row's plan is a function of its bar, its direction and the session's levels (decision 6), built by
  `build_signal_plan` and scored by `score_signal_plan` (Design 2). A row on its session's last
  regular-hours bar gets `plan_r_status` `no_fill`, with no fill and no R (the parent's Design 4).
- **A stored row that is not its bar gets no plan.** A stored row whose entry_time has no bar in the
  frame, or whose entry_price differs from that bar's close by more than half a cent, gets
  `plan_status` `bar_mismatch` and NULL plan prices (decision 6).
- **Basis.** The attach reads the basis in force at each session's open through the range form of
  `read_open_level_basis` (Design 2). A session whose live basis was replaced after the open gives its
  stored signals `basis_replaced`, never the replacement's levels and never a rebuild; a session with
  no stored live basis is built by the builder (Design 2).
- **Parameters.** A plan needs the ticker's level parameters in force on the session (decision 6). The
  range read of parameters is a new one-query function beside `load_level_params`
  (`lib/strat_levels.py:1304`, read), which reads one session per call. A session with no parameters
  in force gives `params_unavailable` (decision 4).

Files this spec would touch: `lib/strat_levels.py` (the range parameter read),
`scripts/run_historical_signals.py` (`--attach-plans`), their tests, the FEAT-SIGNAL-001 catalog
record and traceability entry, and the `(FEAT-SIGNAL-001, DASHBOARD-05)` note row of SITE.

### 2. Reads and writes (Rule 0)

- `--attach-plans`, per ticker: five reads (bars for the window, the stored signals' keys, daily rows
  with their premarket fields, parameters in force over the range, the open basis over the range)
  and one multi-row UPDATE per 1,000 signals, committed per chunk, with a progress line per chunk.
  The range read of parameters is a new one-query function beside `load_level_params`
  (`lib/strat_levels.py:1304`, read), which reads one session per call.

## Order against work in progress

1. **The parent on main.** The parent's implementation is on main before this branch is cut (Depends
   on). The parent's own order (#1948, the recompute, #1823 and #1951 on main before its branch is cut)
   is then already met, and #1951 also changes `lib/strat_levels.py`, which this spec changes.
2. **Clean bars.** No stored signal is given a plan or scored before the month replace and rebuilds
   planned for 2026-11-14 and 11-15 are done and verified, and `historical_signals` has been
   regenerated on those bars by the runbook (REQ-VALID-001). Code and tests may land before; the
   attach run and any scored figure may not.
3. **Level parameters.** The attach run waits until the history-mode calibration of FEAT-STRAT-001 is
   written for the window, which needs the owner's yes of its own (decision 6).

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

**Regenerating history is not part of this design** (decision 6). For the record, the measured local
rate is about 44,000 signals in about 590 s per ticker for 430 sessions; the full stored history is
2,984 sessions a ticker (`clean-set/STATUS.md`, 18:39Z), about 7 times that, so about 68 minutes a
ticker for generation alone (estimate, local speed), over the 1,800 s task timeout, and it deletes
1,557,534 stored rows of the three tickers first (run, db-query-t4nsl).

No new scheduled job, so no new monthly cost line.

## Close-out

After the merge, recorded on the PR, each with its execution name:

1. After the clean bars are verified and the level parameters cover the window: `--attach-plans
   --dry-run` on one ticker (numbers into the PR), then the committed runs, then per ticker and per
   stop rule the share of signals with a stop, the size of 1 R in percent of price, and mean `plan_r`
   and `plan_r_t1` before and after 2026-05-01. No figure with costs.

Source identity. `lib/`, `scripts/` and `tests/` are inside SITE's watched scope. DASHBOARD-05 (the live
signals table) reads `historical_signals`, whose stored rows this changes. Only the
`(FEAT-SIGNAL-001, DASHBOARD-05)` row of the Implementation-source notes table may describe this
implementation, as backend source and local tests only; nothing the element shows changes, since the
parent's `tests/api/test_signal_plan_not_served.py` holds the keys `/api/signals` returns. Every other
SITE byte stays unchanged. The declaration is made here because an implementation PR cannot add it.
After the merge, separately and never as a pre-merge box: main's source and body identity verified in a
fresh clone, the DOC main and staging close-out with the evidence of step 1, the sidecar retired as the
product-delivery skill prescribes, and the plan set to `status: done` on a `docs/` branch.

## Risks

- **A stored row that is not its bar.** Most stored signals of 2026-04 to 2026-09 carry Eastern-label
  times (decision 6). The clean-bars condition (Order 2) holds the run until `historical_signals` is
  regenerated, and the `bar_mismatch` guard, pinned by `test_attach_plans`, gives any row that still
  does not match its bar no plan.
- **Most early signals may have no stop.** Decision 1's cost. The alternates on every row and
  close-out step 1 measure it before anyone relies on `plan_r`.
- **History's premarket fields.** The stored premarket high and low of past sessions were computed from
  the old bars and are used only when filtered with the ticker's thresholds; otherwise the builder
  records the premarket as unavailable or unfiltered and builds without it. The plan keeps that status,
  so such sessions can be counted. Their recompute is the recompute spec's, not this one's.
- **No parameters before 2026-11-12.** Until the history-mode calibration is written for the window,
  every stored signal before 2026-11-12 would get `params_unavailable` (decision 6). Order 3 holds the
  run.

## What was not verified

- How often a signal has a level stop, a spaced T1, or all three targets: not checked. No run has
  built plans for signals with the production builder.
- The speed of `build_signal_plan` and `score_signal_plan`, the bar read for the window, and Cloud Run
  speed against the local machine: not checked.
- That history-mode calibration is point in time: read, not run (`lib/level_calibration.py:11-12`
  says its inputs are dated strictly before `effective_from`). How long it takes for the window: not
  checked.
- The bars' agreement with the vendor: not checked here; this spec waits for that verification.

## Queries run

Read-only, no `--commit`, 2026-11-14, run for the parent; the results cited here are the parent's,
unchanged:

- `db-query-t4nsl`: row counts of `historical_signals` and `signal_alerts` by ticker and run kind;
  columns named like stop, plan, t1 or target on the three signal tables.
- `db-query-8ptk7`: `ticker_level_params` coverage for SPY, QQQ and IWM; `level_basis` coverage of
  `premarket_analysis`; `signal_metrics` counts; `level_param_policy` keys (25, none of #1832's yet).
