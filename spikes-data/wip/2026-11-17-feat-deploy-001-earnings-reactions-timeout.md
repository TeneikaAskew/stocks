---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-17-feat-deploy-001-earnings-reactions-timeout.md
branch: feature/feat-deploy-001-earnings-timeout
pr: null
status: ready
---

# Earnings reactions: a bounded run, a 19,800 s timeout, the Sunday chain and the weekday retirement: implementation plan (spec C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] (lazy SPLITS test) to [8] (catalog, traceability, site notes, audit, gate).

**Goal:** `compute-earnings-reactions` requests a ticker's splits only for an event it can check, stops its vendor requests after 3 consecutive or 10 total request failures and names the rest unavailable, and is deployed with a 19,800 s timeout on both deploy branches; a new `earnings-sunday-chain` job starts the reaction run and then the four Sunday readers, each after its predecessor completed and not before its present time; `deploy_schedulers` swaps the five Sunday entries for the chain's entry only after that entry reads back, stops declaring the two weekday reaction entries, and a one-shot `retire-weekday-earnings` target deletes them. No deploy, job run or scheduler change in production from this branch.

**Architecture:** In `gcp/fetchers/compute_earnings_reactions.py`, a module-level `VendorRequestBudget` paces, counts and classifies every vendor request; `populate_for_tickers` reads the daily windows first, requests SPLITS through the budget at the first event that reaches the split check, and once the budget is spent refuses every remaining ticker by name. `gcp/earnings_sunday_chain.py` drives five Cloud Run executions in order through the `google.cloud.run_v2` surface the repo already uses, with an injected clock and client for the tests. `gcp/deploy.sh` gains two functions (`deploy_earnings_sunday_chain`, `retire_weekday_earnings`), one dispatcher arm, a timezone field in `_schedule_verified`'s read back, and the Sunday swap in `deploy_schedulers`.

**Tech Stack:** Python 3.11, pandas, requests, `google-cloud-run` (`run_v2`, imported lazily: it is in `requirements-gcp.txt:69`, which `build_image` installs, and not in the `requirements.txt` CI installs), bash, pytest (`monkeypatch`, `caplog`, a recording `gcloud` stub), `ast`; `scripts/maintenance/doc_inventory.py`, `scripts/gate/export_model_registry.py`, `scripts/maintenance/doc_source_snapshot.py`, `scripts/maintenance/docs_audit.py`, `scripts/gate/spec_gate.py`.

**Spec:** `docs/superpowers/specs/2026-11-17-feat-deploy-001-earnings-reactions-timeout.md` (approved, merged in #2082). Read beside it: issue #2083 (a round-2 finding on the spec, handled below), the r2 spec `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md` (Split item C, Close-out step 1) and its plan `docs/superpowers/plans/2026-11-17-feat-data-001-spy-qqq-iwm-only.md` (Task 10 defines `fetch_daily_series` and `DailySeriesUnavailable`), and #2060.

**How claims are marked:** "read" is code on `origin/main` 379ad19d0 (2026-11-17; every line number cited is equal on d338c8ed4 and 9d862b05c: #2081 changed only a spec, and #2084 none of the cited code files, catalog record, traceability line or registry rows); "run" was executed for this plan in a scratch copy of d338c8ed4 and discarded; "live" is a read-only `gcloud` call on 2026-11-17 between 21:38Z and 22:23Z; "not checked" means that.

## Blocker found while planning: the model registry rows

**The PR this plan builds cannot pass both `make test` and the gate as the spec stands.** Run on a scratch copy of main with Task 7's scheduler edits applied (run): `tests/meta/test_model_registry_consistency.py` fails three tests until `docs/product/07-MODEL-REGISTRY.md` changes:

- `test_scheduler_table_matches_deploy_sh`: "refresh-earnings-views-weekly is not declared in gcp/deploy.sh" (the listed rows at `:358` `refresh-earnings-views-weekly`, `:362` `premarket-brief-sunday`, `:368` `earnings-sweep-sunday` and `:371` `earnings-long-watchlist-sunday` name entries this change retires);
- `test_every_live_scheduler_is_classified`: "the deliberate-exclusion table names schedulers that gcp/deploy.sh does not declare: ['daily-earnings-refresh-history', 'daily-earnings-refresh-reactions', 'weekly-earnings-refresh-reactions']" (rows `:401`, `:402`), and `earnings-sunday-chain` needs a row;
- `test_scheduler_enumeration_matches_the_canonical_parser`: `assert len(canonical) >= 65` with 61 declared (a test floor, changed in Task 8).

But `check_registry_rows` (`scripts/gate/spec_gate.py:4419-4449`, read; run in `--pr` mode at `:4883-4884`) refuses, on a feature branch, any added or removed registry line that names a `MODEL-*` ID the spec's text never names, and any changed line that names no `MODEL-*` ID at all. Spec C names no `MODEL-*` ID (`grep -c "MODEL-" <spec>` is 0, run). The rows that must go name MODEL-EARN-001 (`:358`, `:368`, `:402`) and MODEL-WATCH-001 (`:371`), and two of the lines that must change name no model (`:362`, `:401`), which the "stray line" rule refuses under any spec. An approved spec does not change in place (`check_changed_specs`, `:2033-2040`, read).

What the gate answered (run, `spec_gate.py --pr <base> <head>` on unreferenced local commits: base = main plus this plan, head = base plus Task 9's rows and the deploy, test and render edits, `PR_HEAD_REF=feature/feat-deploy-001-earnings-timeout`):

- as the spec stands: "docs/product/07-MODEL-REGISTRY.md: changes line(s) naming MODEL-BRIEF-001, MODEL-EARN-001, MODEL-WATCH-001, which docs/superpowers/specs/2026-11-17-feat-deploy-001-earnings-reactions-timeout.md never names";
- with the base's spec text naming the three models: "changes '| `premarket-brief-sunday` | `0 21 * * 0` | `prema', a line naming none of ...'s models";
- with that, and the base's `:362` cell reading `MODEL-BRIEF-001: the same job, weekend refresh` and the `:401` reason cell ending `MODEL-EARN-001 reads its rows through earnings_reactions.`: no registry finding.

`--commit` mode does not run this check: the same staged rows pass it (run).

Routes, for the owner (Task 9 implements the rows under either):

- **A, no gate change.** (1) A `docs/` PR rewrites the last cell of the `:362` and `:401` registry rows so each names the model it relates to (a cell edit only; the tables, names and crons stay; the simulated wording is above; that PR's own gate and suite run: not checked). (2) A superseding spec C r2, approved by the owner, names MODEL-EARN-001, MODEL-WATCH-001 and MODEL-BRIEF-001 as the registry rows this change edits and adds Task 8's and Task 9's files to its done_when. (3) This plan's `spec:` is pointed at r2 on this docs branch **before this plan merges** (once merged, a plan binds one spec and cannot be repointed: the r3 strat plan's gate table, `docs/superpowers/plans/2026-11-17-feat-strat-001-atr-quarter-targets-r3.md`).
- **B, a FEAT-CICD-001 gate change** letting a feature change remove or add the registry rows of the schedulers its own `gcp/deploy.sh` diff stops or starts declaring. A gate file change: red-team pass, pinned copies, two PRs (CLAUDE.md).

Tasks 1 to 8 and 10 to 12 do not depend on the route. Task 9 Step 1 stops until one route is on main.

## Order and preconditions

- **Base: main without r2's implementation.** `git grep -n "def fetch_daily_series" origin/main -- gcp/` is empty and no `feature/feat-data-001-spy-qqq-iwm-only` branch exists on origin (run). Tasks 1 to 3 change `populate_for_tickers` and `main` as they stand on main; r2's Task 10 replaces both (selection, per-ticker commits, `--as-of`, no `--force`). If `fetch_daily_series` is on main when this branch is cut, **stop and ask for this plan to be revised**: Design 2's last bullet then moves both tests onto r2's per-ticker body, and #2083's end-to-end cases land here (below).
- The registry route (above) is on main before Task 9, and before this plan merges if route A's step 3 applies.
- Re-read every anchor on the fork commit and locate edits by quoted content. Open FEAT-DEPLOY-001 PR #1886 edits the same catalog record and traceability line as Task 13 (`docs/product/02-FEATURE-CATALOG.md`, `docs/product/12-PR-ISSUE-TRACEABILITY.md`, read through the GitHub API); open FEAT-CICD-001 PR #2057 edits `scripts/gate/spec_gate.py` and the site source snapshot, after which Task 11 is re-run. Merge `main` in, never rebase a pushed branch.
- The PR is opened as a draft after Task 3 and not marked ready before Task 13. Between Task 7 and Task 9 the registry tests are red by design.
- **#2060 hold.** Nothing here deploys. The hold on `./gcp/deploy.sh fetchers` is lifted only at the owner's Close-out step 1 (spec Decision 1).

### done_when map

| done_when | Item (short) | Tasks |
|---|---|---|
| [0] | `test_splits_requested_only_for_a_checkable_window` | 1 |
| [1] | `test_vendor_failures_stop_the_run` | 2, 3 |
| [2] | `test_compute_earnings_reactions_declares_its_sizing_on_both_branches` | 4 |
| [3] | `test_consumers_start_after_the_reaction_execution` | 5 |
| [4] | `test_sunday_chain_replaces_the_five_sunday_entries` | 6, 7 |
| [5] | `test_retire_weekday_earnings_target` | 10 |
| [6] | `make test`, inventory re-render, pinned cases listed | 4, 6, 7, 8, 9, 10, 13 |
| [7] | Capacity section read through gcloud on the PR day | 12 |
| [8] | catalog, traceability, three site notes, snapshot, docs audit, gate | 11, 13 |

### How #2083 is handled

#2083 (Codex on #2082) found that done_when[1] injects failures only into SPLITS, so an implementation that never records daily-series failures in the budget would pass. Daily-series requests do not exist on main (r2's Task 10 adds `fetch_daily_series`), so this plan pins the defect where it can be pinned now:

- **Bullet 2 (mixed outcomes), in full:** Task 2's `test_vendor_request_budget_counts_every_request_kind` drives one budget with a SPLITS-shaped failure and a daily-series-shaped failure (an exception carrying `reason`, built by `_request_failure`, the shape r2 plan Task 10 gives `DailySeriesUnavailable`): a success of either kind resets the shared consecutive count, and the total limit counts both kinds.
- **Bullet 1 (daily-series transport errors alone):** the same test shows three daily-series transport failures in a row spend the budget and that a spent budget sends nothing; the run-level consequences (cutoff, retained writes, unavailable receipts, exit 1) are kind-agnostic in Task 3 (the run reads `budget.spent`, never the request kind) and are pinned for SPLITS by done_when[1].
- **The defect itself:** Task 3's `test_every_vendor_request_goes_through_the_budget` fails if any function in the module that calls `requests.*` is called other than as `budget.call(<fn>, ...)`. r2's `fetch_daily_series` calls `requests.get`, so r2's rebase cannot reach main with a daily-series request outside the budget.
- **Not covered here:** the end-to-end run with `fetch_daily_series` raising. It needs the function. Task 13 comments on #2083 with the three tests above and leaves it open for r2's implementation PR, which adds the end-to-end case (or, if r2 is on main at the cut, this plan is revised and adds it).

## Global Constraints

- Exact values from the spec: consecutive limit `3`, total limit `10` (module constants `VENDOR_CONSECUTIVE_FAILURE_LIMIT`, `VENDOR_TOTAL_FAILURE_LIMIT`); a failure counts only when its `reason` starts `request_failed` (`_request_failure`, `compute_earnings_reactions.py:607-613`); the stop line `vendor_requests_stopped consecutive=<n> total=<m> remaining=<k> tickers=<list>` at ERROR; the receipt reason for refused events `split_status_unavailable`; exit 1 when the budget was spent.
- Reaction job, both deploy branches: `--memory 2Gi --cpu 1 --max-retries 0 --task-timeout 19800`. Chain job, both branches: `--memory 512Mi --cpu 1 --max-retries 0 --task-timeout 18000 --service-account "${SA_EMAIL}"`, command `python,-m,gcp.earnings_sunday_chain`, no database secret.
- Chain steps, in order: `compute-earnings-reactions` 19:30; `earnings-long-watchlist` 19:45; `refresh-earnings-views` 20:00, no override (the job's default `--mode=weekly`, `gcp/deploy.sh:3048`); `earnings-sweep` 20:30, args `['--options-insights']`; `premarket-brief` 21:00, env `BRIEF_TRIGGERED_BY=cloud-scheduler:earnings-sunday-chain`. The reaction wait ends at 22:30 ET. Exit 0 when all five succeeded, 1 otherwise, 2 on a day that is not Sunday in Eastern time unless `--allow-any-day`.
- Scheduler: `earnings-sunday-chain` at `30 19 * * 0`, `America/New_York`, target job `earnings-sunday-chain`, through `_schedule_verified`. Retired only after its read back passes: `weekly-earnings-refresh-reactions`, `earnings-long-watchlist-sunday`, `refresh-earnings-views-weekly`, `earnings-sweep-sunday`, `premarket-brief-sunday`. No longer declared, never deleted by `deploy_schedulers`: `daily-earnings-refresh-history`, `daily-earnings-refresh-reactions`. Unchanged: `daily-earnings-refresh-calendar`, `weekly-earnings-refresh-calendar`, `weekly-earnings-refresh-history`.
- Not in this PR: r2 Split C's other items (spec Non-goals), per-ticker commits, the order of `fetch-earnings-history` against 19:30, any change to what a reaction contains, the split check, the price basis or an API response.
- Time: every Eastern date and wall time goes through `lib.eastern_time` (`eastern_now`, `localize_assuming_eastern`, CLAUDE.md 3.9); `tests/meta/test_timezone_boundaries.py` stays green.
- No silent fallback (CLAUDE.md 3.7): a missing `GCP_PROJECT` or `GCP_REGION` raises before any start; a vendor failure is named per event; no fabricated reaction.
- **The render step**, after every commit that changes `gcp/deploy.sh` or adds a module under `gcp/` (05-a's `inventory:modules` block lists each with its docstring's first line: the gate refused a probe whose chain module was added after the render, run): `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`, then `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/scripts/test_doc_inventory.py -q`, staging whichever docs changed. Use `--insert`, not `--restore`: only `insert_blocks` re-renders the retry-split counts (`doc_inventory.py:4493`, read); with `--restore` five `test_check_generated_docs.py` cases fail on "claims 46 jobs at --max-retries 0; gcp/deploy.sh declares 48" (run).
- Under `docs/product/` this branch edits only: the FEAT-DEPLOY-001 catalog record and traceability line, the registry rows Task 9 names and the regenerated `generated/model-registry.json`, the renderer-owned blocks and counts of 05-a, 05-c and 05-e, and the three declared rows of `03-SITE-TRACEABILITY.md`'s implementation-source notes.
- Tests are hermetic: no network, no git command in a test, `google.cloud.run_v2` faked through injection. A `gcloud` stub records argv.
- Production: no task writes to production. Task 12's reads are read-only (`env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud ...`).
- Commits: conventional `type(scope): description`, imperative, no AI attribution, no Co-Authored-By line. Every new test has a red then green record in the PR body. No em or en dashes in code comments, log text or docs written for this change.

## Capacity (CLAUDE.md rule 0; spec Design 8), copied into the PR body with Task 12's fresh reads

- **Volume.** Weekday reaction run: at most about 396 tickers (379 reporters, the maximum of 158 weekdays, plus 17 never reacted; `db-query-vzmt8`, spec); measured 3 to 320 a run over 27 runs, the three Sunday runs 132, 278 and 214 (`gcloud logging read`, live, 2026-10-18 to 2026-11-17). Chain: 5 executions a Sunday.
- **Velocity.** At most 1 SPLITS request a ticker whose event reaches a checkable window, paced 0.4 s (`lib/config.py:122-123`); 1 window query a ticker (unchanged count); 1 upsert a run. After a stop: no further request and no window query. Chain: 5 `run_job` calls and one operation poll every 30 s while an execution runs (none while it waits for a start time): about 50 polls on a measured Sunday, about 170 at r2's 70-minute peak.
- **Wall-clock.** Measured 17 s to 775 s without SPLITS (60 executions, 2026-09-09 to 2026-11-17, live); plus about 1.4 s a request (estimate, not measured) at 396 tickers about 554 s, about 22 minutes. The stop adds at most 10 failed requests at about 30.4 s, 304 s (604 s at r2's 60 s): about 27 minutes worst case against 19,800 s. Chain: 19:30 to about 21:02 on time; worst case the reaction wait ends 22:30 and each consumer's wait ends at its task timeout plus 300 s (900, 1,500, 2,100, 2,100 s), so the brief starts by 23:45 and the chain ends by 00:20, inside its 18,000 s (00:30).
- **Cost.** Reaction job at 1 vCPU and 2 GiB, about $0.000022 a second (list prices, not re-read): 775 s about $0.017, the weekday peak about $0.03, six runs a week under $0.80 a month. Chain at 1 vCPU and 0.5 GiB idling about 92 minutes: about $0.11 a run, about $0.46 a month. No new SQL statement. Vendor: up to about 396 SPLITS requests a run against the 600 RPM allowance, paced at 150 RPM; per-call billing not checked.

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in the task that owns the code.

- **A ticker whose SPLITS request failed, with later events that reach the check.** A reasonable person expects one request a ticker and every later checkable event refused `split_status_unavailable`, while events refused earlier keep their own reason; never a second request for the same ticker. Task 1 (`test_a_failed_splits_request_is_held_for_the_tickers_later_events`).
- **A budget spent by the run's last request.** No ticker remains, yet the run made 3 consecutive failures: it logs `vendor_requests_stopped ... remaining=0 tickers=` and exits 1, even though one ticker succeeded (main's all-failed rule alone would exit 0). Task 3 (`test_a_budget_spent_by_the_last_request_still_fails_the_run`).
- **A vendor refusal between transport failures.** A refusal is neither a failure nor a success: it leaves both counts as they were, so timeout, refusal, timeout, timeout stops the run. Task 2 (in `test_vendor_request_budget_counts_every_request_kind`).
- **The Cloud Run API failing during the chain.** A `run_job` that raises is `not_started` with the exception class and the next step starts at its own time; an operation poll that raises is logged and retried, and a consumer whose wait passes its task timeout plus 300 s is `unfinished`, so the brief still starts before midnight. Task 5 (`test_a_refused_start_is_not_started_and_the_next_step_runs`, `test_a_poll_that_raises_is_retried_until_the_step_wait_limit`).
- **A `schedulers` deploy that finds the chain entry already live.** Every routine `schedulers` deploy after Close-out step 2 updates the entry, reads it back with its time zone, and finds the five old names NOT_FOUND, which `_unschedule` treats as done: it exits 0. Task 7 (the "again" case of `test_sunday_chain_replaces_the_five_sunday_entries`).

---

### Task 1: Lazy SPLITS

Spec: § Design 1. Advances done_when[0].

**Files:**
- Modify: `gcp/fetchers/compute_earnings_reactions.py` (`populate_for_tickers` `:772-994`; the `_resolve_tickers` docstring sentence at `:1008-1011`)
- Test: `tests/gcp/test_compute_earnings_reactions.py` (append after `test_every_splits_request_failing_fails_the_run`, `:1550`)

**Interfaces:**
- Produces: `populate_for_tickers` keeps its signature; `counts['split_tickers']` is the number of SPLITS requests made; the per-ticker progress line keeps its shape with `splits=<n>` (event count), `splits=unavailable` or `splits=not_requested`. The appended test section imports `ast`, `logging`, `sys` and `requests` at its top. Test helpers `_window(reported: date) -> pd.DataFrame` (the D-12 to D+5 as-traded window `_two_ticker_run` builds, `:1441-1484`), `_bmo(ticker, reported, report_time='BMO') -> dict` (an `earnings_history` row, fiscal 2025-12-31), and `_reaction_run(monkeypatch, events: list[dict], windows: Callable[[str, date], pd.DataFrame], reply: Callable[[str, int], object]) -> tuple[module, dict]`: like `_two_ticker_run` but it stubs `module.requests.get` (so the real `fetch_splits` and `_request_failure` run; `reply(symbol, n)` returns a `_SplitsReply` or raises, `n` counting from 1) and `module._emit_event_receipts` (pages recorded as `{'events': [...]}`, so `_skips` reads them whether or not a `receipt_sink` is passed); `rec` keys `requests` (symbols in order), `upserts`, `pages`, `sleeps`, `history`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_splits_requested_only_for_a_checkable_window(monkeypatch, caplog):
    events = [_bmo('AAA', date(2026, 2, 2)), _bmo('NOB', date(2026, 2, 2)),
              _bmo('UNK', date(2026, 2, 2), report_time=None), _bmo('SES', date(2026, 2, 1))]
    module, rec = _reaction_run(monkeypatch, events,
                                lambda t, d: _window(d) if t == 'AAA' else pd.DataFrame(),
                                lambda s, n: _SplitsReply({'symbol': s, 'data': []}))
    counts = {}
    with caplog.at_level(logging.INFO, logger=module.log.name):
        written = module.populate_for_tickers(['AAA', 'NOB', 'UNK', 'SES'], observation_ts='2026-02-20T21:01:00Z',
                                              api_key='k', counts=counts)
    assert rec['requests'] == ['AAA'] and rec['sleeps'] == []
    assert written == 1 and {r['ticker'] for r in rec['upserts']} == {'AAA'}
    assert _skips(rec['pages']) == {('NOB:2025-12-31:2026-02-02', 'insufficient_surrounding_daily_bars'),
                                    ('UNK:2025-12-31:2026-02-02', 'unknown_event_timing'),
                                    ('SES:2025-12-31:2026-02-01', 'report_date_is_not_exchange_session')}
    assert (counts['split_tickers'], counts['splits_unavailable']) == (1, 0)
    assert 'splits_unavailable=0 of 1 tickers' in caplog.text
    assert 'ticker=NOB splits=not_requested' in caplog.text
```

  `test_a_failed_splits_request_is_held_for_the_tickers_later_events` (Review Focus 1): ticker `BBB` with three events, BMO 2025-11-03 and BMO 2026-02-02 (both with `_window`) and one with `report_time=None`; every reply `{'Information': 'x'}`. Assert `rec['requests'] == ['BBB']`, the two windowed events skipped `split_status_unavailable`, the third `unknown_event_timing`, `(counts['split_tickers'], counts['splits_unavailable']) == (1, 1)`, nothing upserted, `'ticker=BBB splits=unavailable'` in the log.

  `test_a_run_needing_no_split_list_exits_0` (Design 1, last bullet): `main()` over `NOB` and `UNK` alone (through `_main_argv`, defined here and used by Task 3) asserts `rec['requests'] == []` and a return of 0, so zero requests is not an all-failed run.

- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -q -k "checkable_window or held_for or no_split_list"`. Expected: FAIL, all three. On main the first requests SPLITS for all four tickers (`['AAA', 'NOB', 'UNK', 'SES']`, run with a hermetic driver on main: 4 requests, 1 row written); the second records the BBB skips as three `split_status_unavailable`; the third sees two requests.

- [ ] **Step 3: Implement** in `populate_for_tickers`. Per ticker: read the windows first (`fetch_daily_windows_for_ticker_dates`, moved above the request, Design 1 bullet 3); hold `splits: Splits | None = None` and `splits_failure: SplitsUnavailable | None = None`. At the split check (`:896`, `if not daily.empty and any(...)`), when the window is non-empty: if neither is set, pace (`time.sleep(split_delay)` when `counts['split_tickers'] > 0`, i.e. before every request but the run's first), increment `counts['split_tickers']`, call `fetch_splits`; on `SplitsUnavailable` set `splits_failure`, increment `counts['splits_unavailable']`, log the existing warning with the reason; then, while `splits_failure` is set, emit `_event_receipt(..., 'price_inputs', 'split_status_unavailable', 'write_skipped')` for the event and `continue`. The `Splits` is held for the ticker's later events. The progress line prints `len(splits.events)`, `unavailable` or `not_requested`. Docstrings of `populate_for_tickers` and `_resolve_tickers` say "each ticker whose event reaches the split check" instead of "each ticker".

- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -q`. Expected: PASS, the existing no-adjusted tests unchanged (`test_split_in_loaded_window_skips_the_event` keeps `rec['sleeps'] == [delay]` for its two requesting tickers). CI's integration job (`tests/integration/test_earnings_daily_path_persistence.py:209`) stubs the module's `fetch_splits` and calls `populate_for_tickers(['ANGO'])`; the name is looked up at call time, so the stub still applies after Task 3 (read).

- [ ] **Step 5: Commit** `fix(earnings): request a ticker's splits only for an event the run can check`.

### Task 2: The request budget

Spec: § Design 2, bullet 1 and the last bullet (one budget for every vendor request); #2083 bullet 2 in full and bullet 1 at the budget. Advances done_when[1].

**Files:**
- Modify: `gcp/fetchers/compute_earnings_reactions.py` (after `_request_failure`, `:607-613`)
- Test: `tests/gcp/test_compute_earnings_reactions.py`

**Interfaces:**
- Produces: `VENDOR_CONSECUTIVE_FAILURE_LIMIT = 3`; `VENDOR_TOTAL_FAILURE_LIMIT = 10`; `is_request_failure(exc: BaseException) -> bool` (true when `str(getattr(exc, 'reason', ''))` starts `request_failed`); `class VendorRequestBudget` with `__init__(self, delay_between_calls: float, *, consecutive_limit: int = VENDOR_CONSECUTIVE_FAILURE_LIMIT, total_limit: int = VENDOR_TOTAL_FAILURE_LIMIT)`, attributes `requests`, `consecutive`, `total` (ints from 0), property `spent -> bool` (`consecutive >= consecutive_limit or total >= total_limit`), and `call(self, fetch: Callable[..., T], *args) -> T`: raises `RuntimeError('vendor request budget spent')` when spent (an INTERNAL misuse: callers check `spent` first); otherwise sleeps `delay_between_calls` through the module's `time.sleep` when `requests > 0`, increments `requests`, calls `fetch(*args)`; on return sets `consecutive = 0`; on an exception for which `is_request_failure` holds increments `consecutive` and `total`; re-raises every exception, counted or not. A refusal or any other exception leaves both counts unchanged.

- [ ] **Step 1: Write the failing test.**

```python
def test_vendor_request_budget_counts_every_request_kind(monkeypatch):
    import requests
    from gcp.fetchers import compute_earnings_reactions as module
    from gcp.fetchers.compute_earnings_reactions import SplitsUnavailable, VendorRequestBudget, is_request_failure

    class SeriesUnavailable(Exception):  # the shape r2 plan Task 10 gives DailySeriesUnavailable
        def __init__(self, reason):
            super().__init__(reason)
            self.reason = reason

    def splits_down(): raise SplitsUnavailable(module._request_failure(requests.ConnectTimeout()))
    def series_down(): raise SeriesUnavailable(module._request_failure(requests.ReadTimeout()))
    def series_refused(): raise SeriesUnavailable('Information: limit')
    def ok(): return 'ok'
    sleeps = []
    monkeypatch.setattr(module.time, 'sleep', sleeps.append)

    # #2083 bullet 1, at the budget: three daily-series transport failures in a row spend it
    b = VendorRequestBudget(0.4)
    for _ in range(3):
        with pytest.raises(SeriesUnavailable):
            b.call(series_down)
    assert (b.requests, b.consecutive, b.total, b.spent) == (3, 3, 3, True)
    with pytest.raises(RuntimeError):
        b.call(ok)
    assert b.requests == 3 and sleeps == [0.4, 0.4]

    # #2083 bullet 2: a success of either kind resets the shared consecutive count; the total counts both kinds
    b = VendorRequestBudget(0.0)
    for round_ in range(5):
        for fail in (series_down, splits_down):
            with pytest.raises(Exception):
                b.call(fail)
        if round_ < 4:
            assert b.call(ok) == 'ok' and b.consecutive == 0 and not b.spent
    assert (b.total, b.consecutive, b.spent) == (10, 2, True)

    # a refusal is neither a failure nor a success (Review Focus 3)
    b = VendorRequestBudget(0.0)
    for fetch in (series_down, series_refused, series_down):
        with pytest.raises(SeriesUnavailable):
            b.call(fetch)
    assert (b.consecutive, b.total) == (2, 2)
    assert is_request_failure(SplitsUnavailable('request_failed: HTTP 503'))
    for not_counted in (SplitsUnavailable('Note: x'), SplitsUnavailable('reply_not_json: x'), ValueError('x')):
        assert not is_request_failure(not_counted)
```

- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -q -k counts_every_request_kind`. Expected: FAIL on the import of `VendorRequestBudget`.
- [ ] **Step 3: Implement** the Interfaces above, under a comment citing spec C Design 2 and #2083 (r2's daily-series request records in the same budget).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(earnings): add a vendor request budget shared by every request kind`.

### Task 3: The stop in the run

Spec: § Design 2, bullets 2 and 3; § Design 1, "Pacing". Advances done_when[1]; #2083 (the structural guard).

**Files:**
- Modify: `gcp/fetchers/compute_earnings_reactions.py` (`populate_for_tickers`; `main` `:1096-1159` and its docstring)
- Test: `tests/gcp/test_compute_earnings_reactions.py`

**Interfaces:**
- Consumes: Task 2's `VendorRequestBudget`, Task 1's `_reaction_run`.
- Produces: `counts['vendor_requests_stopped']: bool` (set by `counts.update(...)` at the start beside the two existing keys). Uses Task 1's `_main_argv(monkeypatch, tickers: list[str])`, which sets `sys.argv` to `['compute_earnings_reactions', '--tickers', ','.join(tickers), '--force']` and `ALPHA_VANTAGE_API_KEY=k`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_vendor_failures_stop_the_run(monkeypatch, caplog):
    import requests
    def run(tickers, reply):
        module, rec = _reaction_run(monkeypatch, [_bmo(t, date(2026, 2, 2)) for t in tickers],
                                    lambda t, d: _window(d), reply)
        _main_argv(monkeypatch, tickers)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=module.log.name):
            rc = module.main()
        stops = [l for l in caplog.text.splitlines() if 'vendor_requests_stopped' in l]
        return rc, rec, stops
    def empty(s): return _SplitsReply({'symbol': s, 'data': []})
    def raise_(exc): raise exc('x')
    T = [f'T{i:02d}' for i in range(1, 21)]

    rc, rec, stops = run(T[:12], lambda s, n: raise_(requests.ConnectTimeout) if n in (3, 4, 5) else empty(s))
    assert rc == 1 and rec['requests'] == T[:5]
    assert sorted({r['ticker'] for r in rec['upserts']}) == T[:2]
    assert {e for e, r in _skips(rec['pages']) if r == 'split_status_unavailable'} == \
        {f'{t}:2025-12-31:2026-02-02' for t in T[2:12]}
    assert len(stops) == 1 and 'consecutive=3' in stops[0] and stops[0].endswith('tickers=' + ','.join(T[5:12]))

    rc, rec, stops = run(T, lambda s, n: raise_(requests.ReadTimeout) if n % 2 else empty(s))
    assert rc == 1 and len(rec['requests']) == 19 and len(stops) == 1 and 'total=10' in stops[0]

    rc, rec, stops = run(T[:12], lambda s, n: _SplitsReply({'Information': 'x'}))
    assert rc == 1 and len(rec['requests']) == 12 and stops == []

    rc, rec, stops = run(T[:3], lambda s, n: raise_(requests.ConnectTimeout) if n == 2 else empty(s))
    assert rc == 0 and len(rec['requests']) == 3 and stops == []
```

  `test_a_budget_spent_by_the_last_request_still_fails_the_run` (Review Focus 2): four tickers, requests 2 to 4 raise `ConnectTimeout`; `main() == 1`, one stop line containing `remaining=0`, the first ticker's reaction upserted.

  `test_every_vendor_request_goes_through_the_budget` (#2083): parse the module with `ast`; `requesters` is the set of module-level functions whose body holds a call `requests.<attr>(...)`; assert `'fetch_splits' in requesters`; assert no call anywhere in the module has `func` an `ast.Name` in `requesters`; assert the set of first positional `ast.Name` arguments of `<x>.call(...)` calls equals `requesters`.

- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py -q -k "stop_the_run or last_request or through_the_budget"`. Expected: FAIL. On main the first case makes 12 requests, writes 9 tickers and exits 0 (run); after Task 1 `fetch_splits` is still called directly, so the guard fails.

- [ ] **Step 3: Implement.** `populate_for_tickers` builds one `VendorRequestBudget(AlphaVantageConfig().delay_between_calls)` (the budget now owns the pacing; Task 1's sleep goes) and requests through `budget.call(fetch_splits, ticker, api_key)`. At the top of each ticker, when `budget.spent`: every event of this and every later ticker is refused `split_status_unavailable` (no window query), each such ticker counts in `counts['splits_unavailable']`, and the loop ends. After the loop, when `budget.spent`: `log.error('vendor_requests_stopped consecutive=%d total=%d remaining=%d tickers=%s', ...)` once, with the never-requested tickers comma-joined in run order (empty when none), and `counts['vendor_requests_stopped'] = True`. Rows already computed are upserted as today. `main` returns 1 when `counts['vendor_requests_stopped']`, before the existing all-failed rule; its docstring names the three exit-1 cases.

- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_compute_earnings_reactions.py tests/meta/test_timezone_boundaries.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(earnings): stop vendor requests after 3 consecutive or 10 failures and fail the run`. Push; open the PR as a draft titled `FEAT-DEPLOY-001: bound the earnings reaction run and order its Sunday readers`.

### Task 4: The reaction job's sizing on both deploy branches

Spec: § Design 3. Advances done_when[2] and [6].

**Files:**
- Modify: `gcp/deploy.sh` (`deploy_compute_earnings_reactions`, `:3001-3023`, and its comment)
- Modify: `tests/gcp/test_deploy_reachability.py` (the stub at `:374-421`; a new section)
- Modify: `tests/scripts/test_doc_inventory.py` (`:474`, `:499`: they pinned the reaction job's old sizing as the config-drift example)
- Modify: the 05-a/05-c/05-e renders (the render step)

**Interfaces:**
- Produces: `_STATEFUL_GCLOUD` gains `STUB_FAIL_RUN_CREATE=1` (a `run jobs create` exits 1); test helper `_run_deploy_fn(tmp_path, fn: str, **stub_env) -> list[list[str]]` that runs `fn` with its `_closure` defined under `set -uo pipefail`, `PROJECT_ID=proj REGION=us-east1 SA_EMAIL=sa@proj.iam.gserviceaccount.com IMAGE_REF=img@sha256:0 DB_SECRET_FLAG=--set-secrets=DB_PASS=db-trading-pass:latest ENV_STRING=DB_NAME=trading`, and returns the recorded `run jobs create|update` argv lists; `_flag(argv, name) -> str | None`.

- [ ] **Step 1: Write the failing test** `test_compute_earnings_reactions_declares_its_sizing_on_both_branches`: with the create succeeding, the calls are exactly one `create` of `compute-earnings-reactions`; with `STUB_FAIL_RUN_CREATE=1`, a `create` then an `update`, both of `compute-earnings-reactions`; every call has `_flag(a, '--task-timeout') == '19800'`, `--max-retries` `'0'`, `--memory` `'2Gi'`, `--cpu` `'1'`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py -q -k declares_its_sizing`. Expected: FAIL (main: create 1800, `--max-retries 1`, 1Gi; update 1800 with neither flag).
- [ ] **Step 3: Implement.** Both branches pass `--memory 2Gi --cpu 1 --max-retries 0 --task-timeout 19800`. Replace the comment: the job reads the database and makes one AlphaVantage SPLITS request per ticker whose event reaches the split check, stops after 3 consecutive or 10 request failures, and 19,800 s is 4 times r2's 4,804 s bounded worst case (spec Design 3 and Capacity).
- [ ] **Step 4: Change the two drift tests**: `:474` becomes `assert not any("compute-earnings-reactions.memory" in d for d in drift), drift` (the declaration now equals the snapshot's 2Gi; keep the db-query assertion as the live example), `:499` expects `"19800"` and `"5400"`. Run the render step; expected: 05-a `updated` (the reaction job's row and the retry split: one job moves from `--max-retries 1` to `0`).
- [ ] **Step 5: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py tests/gcp/test_deploy_flag_syntax.py tests/scripts/test_doc_inventory.py tests/scripts/test_check_generated_docs.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** `fix(deploy): size compute-earnings-reactions at 19800 s, 2Gi and 0 retries on both branches`.

### Task 5: The Sunday chain

Spec: § Design 4 (all but "Deploy"); § Approaches 5. Advances done_when[3].

**Files:**
- Create: `gcp/earnings_sunday_chain.py`
- Test: `tests/gcp/test_earnings_sunday_chain.py`

**Interfaces:**
- Produces, in `gcp/earnings_sunday_chain.py`:
  - `@dataclass(frozen=True) class Step: job: str; not_before: datetime.time; wait_seconds: int | None; args: tuple[str, ...] = (); env: tuple[tuple[str, str], ...] = ()` (`wait_seconds` None for the reaction, whose wait ends at `REACTION_WAIT_ENDS`).
  - `STEPS: tuple[Step, ...]`, the Global Constraints' five, with `wait_seconds` 900, 1,500, 2,100 and 2,100 for the four consumers: each job's task timeout in `gcp/deploy.sh` (600, 1,200, 1,800, 1,800, live: the same) plus `WAIT_MARGIN_SECONDS = 300`. The comment above `STEPS` carries the reason `--options-insights` is required (moved from the `earnings-sweep-sunday` comment, `gcp/deploy.sh:4837-4849`).
  - `REACTION_WAIT_ENDS = time(22, 30)`; `POLL_SECONDS = 30`.
  - `@dataclass class StepResult: job: str; execution: str | None; not_before: datetime; started: datetime | None; completed: datetime | None; outcome: str` (`succeeded`, `failed`, `unfinished`, `not_started`).
  - `run_chain(run_v2, *, project: str, region: str, run_date: date, now: Callable[[], datetime], sleep: Callable[[float], None]) -> list[StepResult]`.
  - `main(argv: list[str] | None = None, *, run_v2=None, now: Callable[[], datetime] | None = None, sleep: Callable[[float], None] | None = None) -> int`; defaults `importlib.import_module('google.cloud.run_v2')`, `lib.eastern_time.eastern_now`, `time.sleep`; `--allow-any-day`.
- The `run_v2` surface used, exactly: `run_v2.JobsClient().run_job(request=run_v2.RunJobRequest(name=f'projects/{project}/locations/{region}/jobs/{job}', overrides=...))`, `overrides` only for a step with args or env: `run_v2.RunJobRequest.Overrides(container_overrides=[run_v2.RunJobRequest.Overrides.ContainerOverride(args=[...])])` or `...ContainerOverride(env=[run_v2.EnvVar(name=..., value=...)])`. The returned operation: `op.done() -> bool` (each call refreshes it), `op.result()` (an `Execution`, or raises for a failed one: not checked, spec "What was not verified"), `op.metadata` (the `Execution`: `name`, `succeeded_count`, `failed_count`, `cancelled_count`).

- [ ] **Step 1: Write the fakes and the done_when test.** The file imports `from gcp import earnings_sunday_chain as chain` and `from lib.eastern_time import localize_assuming_eastern`. `FakeClock(start)` with `now()` and `sleep(seconds)` advancing it. `chain_fakes(monkeypatch, start: datetime, *, reaction: timedelta, modes: dict[str, str] | None = None) -> tuple[FakeClock, SimpleNamespace]` sets `GCP_PROJECT=proj` and `GCP_REGION=us-east1` and returns a clock at `start` and a fake `run_v2` module (`types.SimpleNamespace` with the classes above): the reaction's execution completes `reaction` after its start, each consumer `SECONDS[job]` after its start; `modes[job]` is `'ok'` (default), `'failed_counts'` (`result()` returns an execution with `failed_count=1`) or `'failed_raises'` (`result()` raises, `metadata` has `failed_count=1`). The fake records `started` (`(job, at, args, env)` per `run_job`, in call order, `env` as name and value pairs), `names` (the request names) and `completed` (job to completion time); `completions(run_v2)` is the completion times of the first four started jobs, in order. `NOT_BEFORE` maps each job to its `Step.not_before`.

```python
SUNDAY = localize_assuming_eastern(datetime(2026, 11, 22, 19, 30))
CONSUMERS = ['earnings-long-watchlist', 'refresh-earnings-views', 'earnings-sweep', 'premarket-brief']
SECONDS = {'earnings-long-watchlist': 26, 'refresh-earnings-views': 52, 'earnings-sweep': 657, 'premarket-brief': 110}

def test_consumers_start_after_the_reaction_execution(monkeypatch, caplog):
    # the 70-minute peak: each consumer after its predecessor completed, none before its time
    clock, run_v2 = chain_fakes(monkeypatch, SUNDAY, reaction=timedelta(minutes=70))
    assert chain.main([], run_v2=run_v2, now=clock.now, sleep=clock.sleep) == 0
    started = run_v2.started  # [(job, at, args, env), ...] in call order
    assert [s[0] for s in started] == ['compute-earnings-reactions'] + CONSUMERS
    assert started[0][1] == SUNDAY
    for (job, at, _, _), prev_done in zip(started[1:], completions(run_v2)):
        assert at >= prev_done and at.time() >= NOT_BEFORE[job]
    assert started[3][2] == ['--options-insights']
    assert started[4][3] == [('BRIEF_TRIGGERED_BY', 'cloud-scheduler:earnings-sunday-chain')]
    assert run_v2.names[0] == 'projects/proj/locations/us-east1/jobs/compute-earnings-reactions'
    assert caplog.text.count('step=') == 5

    # on time: the four start at their present times
    clock, run_v2 = chain_fakes(monkeypatch, SUNDAY, reaction=timedelta(minutes=8))
    assert chain.main([], run_v2=run_v2, now=clock.now, sleep=clock.sleep) == 0
    assert [s[1].strftime('%H:%M:%S') for s in run_v2.started[1:]] == ['19:45:00', '20:00:00', '20:30:00', '21:00:00']

    # a failed consumer, both failure shapes, does not stop the next one
    clock, run_v2 = chain_fakes(monkeypatch, SUNDAY, reaction=timedelta(minutes=8),
                                modes={'refresh-earnings-views': 'failed_raises', 'earnings-sweep': 'failed_counts'})
    assert chain.main([], run_v2=run_v2, now=clock.now, sleep=clock.sleep) == 1
    assert [s[0] for s in run_v2.started][-1] == 'premarket-brief'

    # a reaction still running at 22:30: logged, the four still start, exit 1
    clock, run_v2 = chain_fakes(monkeypatch, SUNDAY, reaction=timedelta(hours=5))
    assert chain.main([], run_v2=run_v2, now=clock.now, sleep=clock.sleep) == 1
    assert 'reactions_unfinished' in caplog.text and [s[0] for s in run_v2.started][1:] == CONSUMERS
    assert run_v2.started[1][1].strftime('%H:%M') == '22:30'

    # a Monday: exit 2, nothing started
    clock, run_v2 = chain_fakes(monkeypatch, SUNDAY + timedelta(days=1), reaction=timedelta(minutes=8))
    assert chain.main([], run_v2=run_v2, now=clock.now, sleep=clock.sleep) == 2 and run_v2.started == []
```

  Also: `test_a_refused_start_is_not_started_and_the_next_step_runs` (`run_job` raises `RuntimeError` for `earnings-long-watchlist`: its `step=` line says `outcome=not_started` and `error=RuntimeError`, `refresh-earnings-views` starts at 20:00, exit 1); `test_a_poll_that_raises_is_retried_until_the_step_wait_limit` (the sweep's `done()` raises `ConnectionError` on every poll: the log names `poll_error=ConnectionError`, the step is `unfinished` 2,100 s after its start, the brief still starts, exit 1); `test_project_and_region_come_from_the_environment` (without `GCP_REGION`, `main` raises `RuntimeError` naming it and starts nothing); `test_consumer_wait_limits_are_their_task_timeouts_plus_the_margin` (`scripts.maintenance.doc_inventory.deploy_jobs(REPO)`'s `task_timeout` for each consumer plus 300 equals its `wait_seconds`); `test_allow_any_day_runs_on_a_monday`.

- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_earnings_sunday_chain.py -q`. Expected: FAIL (`ModuleNotFoundError: gcp.earnings_sunday_chain`).
- [ ] **Step 3: Implement.** `main` parses `--allow-any-day`, reads `GCP_PROJECT` and `GCP_REGION` (absent raises `RuntimeError` naming the variable), resolves `run_v2`, `now`, `sleep`, and returns 2 with one log line when `now().weekday() != 6` and the flag is absent. `run_chain` takes `run_date = now().date()`; per step: `not_before = localize_assuming_eastern(datetime.combine(run_date, step.not_before))`; sleep until `now() >= not_before`; `run_job` (an exception: `not_started`, logged with its class, next step); then poll `op.done()` every `POLL_SECONDS` (never past the wait end: `REACTION_WAIT_ENDS` on `run_date` for the reaction, `started + wait_seconds` for a consumer); a `done()` that raises is logged `poll_error=<class>` and polled again; at the wait end the step is `unfinished` (for the reaction, also `log.error('reactions_unfinished execution=%s', ...)`); when done, the execution is `op.result()`, or `op.metadata` if that raises, and the outcome is `succeeded` only when `failed_count == 0`, `cancelled_count == 0` and `succeeded_count >= 1`. Every step logs `step=<job> execution=<name> not_before=<ET> started=<ET> completed=<ET> outcome=<outcome>` (times as Eastern ISO seconds, `-` when unknown). Exit 0 only when all five are `succeeded`.
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_earnings_sunday_chain.py tests/meta/test_timezone_boundaries.py -q`. Expected: PASS. Then the render step: 05-a `updated` (its `inventory:modules` block gains `gcp/earnings_sunday_chain.py`).
- [ ] **Step 5: Commit** `feat(earnings): chain the Sunday reaction run and its four readers by completion`.

### Task 6: The chain job's deploy function

Spec: § Design 4, "Deploy". Advances done_when[4] (the chain created by `deploy_fetchers`) and [6].

**Files:**
- Modify: `gcp/deploy.sh` (new `deploy_earnings_sunday_chain` after `deploy_compute_earnings_reactions`; one line in `deploy_fetchers` after `deploy_compute_earnings_reactions`, `:3218`)
- Test: `tests/gcp/test_deploy_reachability.py`

- [ ] **Step 1: Write the failing test** `test_earnings_sunday_chain_declares_its_sizing_on_both_branches`, through Task 4's `_run_deploy_fn`: with the create succeeding one `create`, with `STUB_FAIL_RUN_CREATE=1` a `create` then an `update`, all of `earnings-sunday-chain`; each carries `--memory 512Mi`, `--cpu 1`, `--max-retries 0`, `--task-timeout 18000`, `--service-account sa@proj.iam.gserviceaccount.com`, `--command python,-m,gcp.earnings_sunday_chain`, `--set-env-vars GCP_PROJECT=proj,GCP_REGION=us-east1`, and no `--set-secrets` argument; and `"earnings-sunday-chain" in _created_by(_closure({"deploy_fetchers"}))`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py -q -k chain_declares`. Expected: FAIL (no such function).
- [ ] **Step 3: Implement** the function in the create-or-update shape of its neighbours, with the flags above on both branches and `--image "${IMAGE_REF:?build_image has not run in this invocation}"`; no `${DB_SECRET_FLAG}` and no `${ENV_STRING}` (it reads no database). A comment states its capacity (Design 4, Deploy). Run the render step; expected: 05-a `updated` (one job row, the retry split).
- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py tests/gcp/test_deploy_flag_syntax.py tests/scripts/test_doc_inventory.py tests/scripts/test_check_generated_docs.py -q`. Expected: PASS (read: the reconcile test asserts membership in `jobs_repo_only`, which gains `earnings-sunday-chain`, not equality).
- [ ] **Step 5: Commit** `feat(deploy): deploy the earnings-sunday-chain job with the fetchers`.

### Task 7: The Sunday scheduler swap

Spec: § Design 5, bullets 1, 2 and 4. Advances done_when[4] and [6].

**Files:**
- Modify: `gcp/deploy.sh`: `_schedule_verified` read back (`:4205-4211`); `deploy_schedulers`: the `premarket-brief-sunday` line and its comment (`:4504-4508`), the earnings block (`:4805-4859`)
- Modify: `tests/gcp/test_deploy_reachability.py` (the stub; `_UNCHANGED` at `:432`)

**Interfaces:**
- Produces: `_schedule_verified` reads back `value(schedule,timeZone,httpTarget.uri,state)` and compares it with `${CRON}\tAmerica/New_York\t${uri}\tENABLED`, its error naming all four. **Choice:** done_when[4] requires a differing time zone to block the deletes and today's read back has no time zone; every live entry `_schedule_verified` manages reads `America/New_York` (`premarket-refresh-late`, `news-sentiment-hourly`, `news-topics-hourly`, `sec-filings-intraday`; live), and the four-field read back prints `20 9 * * 1-5<TAB>America/New_York<TAB>https://...fetch-premarket-refresh:run<TAB>ENABLED` (live).
- Stub additions to `_STATEFUL_GCLOUD`: describe output field `timeZone` (from the stored `time_zone`); `STUB_ABSENT_JOBS` (comma list: `run jobs describe NAME` exits 1 with `ERROR: (gcloud.run.jobs.describe) Cannot find job [NAME].`); `STUB_FAIL_WRITE` (comma list: a scheduler `create` or `update` of NAME exits 1); scheduler `delete NAME` writes `sched/NAME.deleted`, after which `describe NAME` answers NOT_FOUND, and exits 1 for names in `STUB_FAIL_DELETE`; `STUB_DRIFT=NAME:FIELD:VALUE` overrides one stored field (`schedule`, `time_zone`, `uri`, `state`) in NAME's read back. `STUB_DRIFT_CRON` stays for the existing test.

- [ ] **Step 1: Write the failing test.**

```python
_SUNDAY_OLD = ["weekly-earnings-refresh-reactions", "earnings-long-watchlist-sunday",
               "refresh-earnings-views-weekly", "earnings-sweep-sunday", "premarket-brief-sunday"]
_WEEKDAY_OLD = ["daily-earnings-refresh-history", "daily-earnings-refresh-reactions"]

def _sched_calls(argv, verbs, names):
    return [a for a in argv if a[:2] == ["scheduler", "jobs"] and a[2] in verbs
            and (a[4] if a[2] in ("create", "update") else a[3]) in names]

def test_sunday_chain_replaces_the_five_sunday_entries(tmp_path):
    seeded = ",".join(_SUNDAY_OLD + _WEEKDAY_OLD)
    r, argv, sched = _run_schedulers(tmp_path / "swap", STUB_EXISTING=seeded)
    assert r.stdout.endswith("All schedulers configured.\nrc=0\n"), r.stdout[-800:] + r.stderr[-800:]
    chain = sched["earnings-sunday-chain"]
    assert (chain["schedule"], chain["time_zone"], chain["uri"], chain["state"]) == \
        ("30 19 * * 0", "America/New_York", _URI.format("earnings-sunday-chain"), "ENABLED")
    readback = max(i for i, a in enumerate(argv) if a[:4] == ["scheduler", "jobs", "describe", "earnings-sunday-chain"])
    deletes = {a[3]: i for i, a in enumerate(argv) if a[:3] == ["scheduler", "jobs", "delete"]}
    assert set(deletes) == set(_SUNDAY_OLD) and min(deletes.values()) > readback
    assert _sched_calls(argv, ("create", "update", "delete"), _WEEKDAY_OLD) == []

    for case, env in (("absent", {"STUB_ABSENT_JOBS": "earnings-sunday-chain"}),
                      ("create", {"STUB_FAIL_WRITE": "earnings-sunday-chain"}),
                      ("cron", {"STUB_DRIFT": "earnings-sunday-chain:schedule:0 0 * * *"}),
                      ("zone", {"STUB_DRIFT": "earnings-sunday-chain:time_zone:UTC"}),
                      ("uri", {"STUB_DRIFT": "earnings-sunday-chain:uri:" + _URI.format("earnings-sweep")}),
                      ("state", {"STUB_DRIFT": "earnings-sunday-chain:state:PAUSED"})):
        r, argv, sched = _run_schedulers(tmp_path / case, STUB_EXISTING=seeded, **env)
        assert r.stdout.endswith("rc=1\n") and "All schedulers configured." not in r.stdout, case
        assert _sched_calls(argv, ("delete",), _SUNDAY_OLD) == [], case
        assert _sched_calls(argv, ("create", "update", "delete"), _WEEKDAY_OLD) == [], case
        if case == "absent":
            assert "earnings-sunday-chain" not in sched and "job earnings-sunday-chain not found" in r.stderr

    # Review Focus 5: a later deploy over a live chain entry converges and exits 0
    r, argv, _ = _run_schedulers(tmp_path / "again", STUB_EXISTING="earnings-sunday-chain")
    assert r.stdout.endswith("rc=0\n") and _sched_calls(argv, ("update",), ["earnings-sunday-chain"])

    assert "earnings-sunday-chain" in SCHEDULED and not (set(_SUNDAY_OLD + _WEEKDAY_OLD) & SCHEDULED)
    assert "earnings-sunday-chain" in _created_by(_closure({"deploy_fetchers"}))
```

- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py -q -k replaces_the_five`. Expected: FAIL (`KeyError: 'earnings-sunday-chain'`).
- [ ] **Step 3: Implement.**
  - `_schedule_verified` as in Interfaces; its comment says it now reads back the time zone.
  - Delete the `premarket-brief-sunday` line and its four comment lines; the two `daily-earnings-refresh-history` and `-reactions` lines; the `weekly-earnings-refresh-reactions` line; `earnings-long-watchlist-sunday` and its comment; the `earnings-sweep-sunday` call and its comment (the rationale moved in Task 5); `refresh-earnings-views-weekly` and the weekly half of the views comment (the `_schedule_args "refresh-earnings-views-daily"` line stays).
  - After `weekly-earnings-refresh-history`, this block, written so `scripts/maintenance/doc_inventory.py`'s reader sees the declaration: it matches `_schedule_verified` only at a line start after optional `if` (`doc_inventory.py:329-331`, read; a `describe ... && _schedule_verified` line was not parsed, 60 entries instead of 61, run):

```bash
    if gcloud run jobs describe earnings-sunday-chain --region "${REGION}" --quiet >/dev/null 2>&1; then
        if _schedule_verified "earnings-sunday-chain" "30 19 * * 0" "earnings-sunday-chain"; then
            for OBSOLETE in weekly-earnings-refresh-reactions earnings-long-watchlist-sunday \
                refresh-earnings-views-weekly earnings-sweep-sunday premarket-brief-sunday; do
                _unschedule "${OBSOLETE}" || SCHEDULER_FAILURES=$((SCHEDULER_FAILURES + 1))
            done
        else
            echo "  earnings-sunday-chain NOT verified; the five Sunday entries left in place." >&2
            SCHEDULER_FAILURES=$((SCHEDULER_FAILURES + 1))
        fi
    else
        echo "  ERROR: job earnings-sunday-chain not found; the five Sunday entries left in place (run ./gcp/deploy.sh fetchers first)." >&2
        SCHEDULER_FAILURES=$((SCHEDULER_FAILURES + 1))
    fi
```

  - Rewrite the comment block `:4805-4826` (Design 5, last bullet): weekdays, calendar 19:00, history 19:15 and reactions 19:30 until `retire-weekday-earnings` (Close-out step 4); Sundays, calendar and history on their crons, then `earnings-sunday-chain` at 19:30, which starts the reaction run and its four readers by completion (`gcp/earnings_sunday_chain.py`).
- [ ] **Step 4: Drop** `"premarket-brief-sunday"` from `_UNCHANGED` (`:432`; it pinned a retired scheduler). Run `bash -n gcp/deploy.sh` (no output), then `python3 -m pytest tests/gcp/test_deploy_reachability.py -q`. Expected: PASS. Run the render step; expected: 05-a `updated` (scheduler rows, reconcile block), 05-c `updated` (the `blast` and `graph` blocks, run). Expected red until Tasks 8 and 9: `test_reconcile_against_snapshot_reports_the_known_deltas`, `tests/meta/test_stage_one_run_hours.py` (two), `tests/meta/test_model_registry_consistency.py` (three).
- [ ] **Step 5: Commit** `feat(deploy): swap the five Sunday earnings entries for earnings-sunday-chain after it reads back`.

### Task 8: The tests that read the declared schedulers

Spec: done_when[6] (make test; the changed cases listed). Not in the spec's list of three files: `tests/meta/test_stage_one_run_hours.py` and `tests/meta/test_model_registry_consistency.py` also pin the declared Sunday entries (run: both fail after Task 7).

**Files:**
- Modify: `tests/scripts/test_doc_inventory.py:262-277`
- Modify: `tests/meta/test_stage_one_run_hours.py` (`:57-60`, `:113-120`, `:131`, `:172-197`)
- Modify: `tests/meta/test_model_registry_consistency.py:419-424`

- [ ] **Step 1: Reconcile expectations.** `schedulers_live_only` becomes `["daily-earnings-refresh-history", "daily-earnings-refresh-reactions", "earnings-long-watchlist-sunday", "evaluate-ew-strikes-daily", "premarket-brief-sunday", "refresh-earnings-views-weekly", "weekly-earnings-refresh-reactions"]` and `schedulers_repo_only` becomes `["earnings-sunday-chain", "premarket-brief-late", "premarket-refresh-late"]` (both run on the scratch copy); the comment says why: the five Sunday entries and the two weekday entries are live in the 2026-09-07 snapshot and no longer declared (spec C), and the chain's entry is repo-only until the owner's deploy.
- [ ] **Step 2: The stage-one evening rule follows the chain.** Its invariant (refresh-earnings-views' only evening run is `--mode=weekly`) now holds through the chain step, which no scheduler entry shows. `WEEKLY_VIEWS_ENTRY` becomes `WEEKLY_VIEWS_RUN = ("refresh-earnings-views", "20:00", ["--mode=weekly"])`. Add `chain_evening_runs(root, steps) -> list[tuple[str, str, list[str]]]`: for each `gcp.earnings_sunday_chain.STEPS` step whose job is in `NO_JOBS` and whose `not_before.hour` is in `EVENING_HOURS`, `(job, not_before as HH:MM, list(step.args) or the job's deploy args)`. `test_no_job_whose_sites_are_right_by_schedule_runs_in_the_evening` asserts `evening_entries(REPO) == []` and `chain_evening_runs(REPO, STEPS) == [WEEKLY_VIEWS_RUN]`. `test_a_moved_schedule_or_a_changed_mode_fails`: (a) expects `[("realtime-gex-daily", ...)]` alone; (b) after `_weekly_job_args_become_daily`, `chain_evening_runs(job, STEPS) == [("refresh-earnings-views", "20:00", ["--mode=daily"])]`; (c) a copy of `STEPS` whose views step carries `args=("--mode=daily",)` gives the same. `test_the_weekly_views_run_never_reaches_the_daily_sites` reads `WEEKLY_VIEWS_RUN[2]`.
- [ ] **Step 3: The declared-count floor** `assert len(canonical) >= 65` becomes `>= 61`, and its message adds that spec C retired seven entries and added one (61 declared, run).
- [ ] **Step 4: Run** `python3 -m pytest tests/scripts/test_doc_inventory.py tests/meta/test_stage_one_run_hours.py -q`. Expected: PASS. `tests/meta/test_model_registry_consistency.py` stays red on the two row tests until Task 9.
- [ ] **Step 5: Commit** `test(deploy): follow the Sunday readers from the scheduler entries to the chain steps`.

### Task 9: The model registry rows

Spec: done_when[6] (`make test`). **Blocked**: see "Blocker found while planning". The rows below are the same under route A or B.

**Files:**
- Modify: `docs/product/07-MODEL-REGISTRY.md` (`:358`, `:362`, `:368`, `:371`, `:401`, `:402`; one added row)
- Modify: `docs/product/generated/model-registry.json` (regenerated)

- [ ] **Step 1: Check the route is on main.** Route A: the cell edits of `:362` and `:401` and an approved spec naming MODEL-EARN-001, MODEL-WATCH-001 and MODEL-BRIEF-001 are on `origin/main`, and this plan's `spec:` names that spec. Route B: the gate change is on main. Neither: **stop** and report; do not edit the registry.
- [ ] **Step 2: Run** `python3 -m pytest tests/meta/test_model_registry_consistency.py -q -k "scheduler_table_matches or every_live_scheduler_is_classified"`. Expected: FAIL as in the Blocker section.
- [ ] **Step 3: Edit the rows.** Remove the listed rows `refresh-earnings-views-weekly`, `premarket-brief-sunday`, `earnings-sweep-sunday` and `earnings-long-watchlist-sunday`. Add, after `refresh-earnings-views-daily`: `` | `earnings-sunday-chain` | `30 19 * * 0` | `earnings-sunday-chain` | MODEL-EARN-001, MODEL-WATCH-001 and MODEL-BRIEF-001: starts, each after the one before has completed and not before its time, `compute-earnings-reactions` (19:30), `earnings-long-watchlist` (19:45, MODEL-WATCH-001), `refresh-earnings-views` in its default `--mode=weekly` (20:00, MODEL-EARN-001), `earnings-sweep --options-insights` (20:30, MODEL-EARN-001, writes `earnings_calibration`) and `premarket-brief` (21:00, MODEL-BRIEF-001, the Sunday weekly brief); `gcp/earnings_sunday_chain.py` | ``. In the exclusion table, the first cell of the history row becomes `` `weekly-earnings-refresh-history` `` (rest unchanged) and the reactions row is removed (its job is now started by the chain, whose row names it). No date in any edited line.
- [ ] **Step 4: Regenerate** `python3 scripts/gate/export_model_registry.py`, then run `python3 -m pytest tests/meta/test_model_registry_consistency.py tests/scripts/test_export_model_registry.py -q`. Expected: PASS.
- [ ] **Step 5: Gate:** `python3 scripts/gate/spec_gate.py --pr origin/main` on the committed head; expected `spec gate ok`. If `check_registry_rows` refuses a line, stop and report its message.
- [ ] **Step 6: Commit** `docs(registry): classify earnings-sunday-chain and drop the retired earnings entries`.

### Task 10: The weekday retirement target

Spec: § Design 5, bullet 3; § Close-out step 4. Advances done_when[5].

**Files:**
- Modify: `gcp/deploy.sh` (new `retire_weekday_earnings` after `_unschedule`, `:4160-4176`; the credential-exempt list `:1090-1093`; a dispatcher arm after `schedulers)`, `:5456`; one help line after the `schedulers` line, `:5578`)
- Test: `tests/gcp/test_deploy_reachability.py`

- [ ] **Step 1: Write the failing test** `test_retire_weekday_earnings_target`: run `bash gcp/deploy.sh retire-weekday-earnings` from `REPO` with the Task 7 stub first on `PATH`, `OUT`, `PROJECT_ID=proj` and `STUB_EXISTING=daily-earnings-refresh-history,daily-earnings-refresh-reactions`. Assert exit 0; for each name, a `scheduler jobs delete <name>` followed by a `scheduler jobs describe <name>` (the read back) and `<name>: NOT_FOUND` in stdout; every recorded argv is a `scheduler jobs describe|delete` of one of the two names (no `builds`, no `run`, no other scheduler); with `STUB_FAIL_DELETE=daily-earnings-refresh-reactions`, exit non-zero and the history entry still deleted. Also assert `"retire-weekday-earnings" in _flag_exempt_targets()`.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py -q -k retire_weekday`. Expected: FAIL (main prints `ERROR: unknown target` and exits 2).
- [ ] **Step 3: Implement** `retire_weekday_earnings`: for each of the two names, `_unschedule NAME` (a failure counts), then `gcloud scheduler jobs describe NAME --location "${REGION}" --format="value(name)"`: success counts as a failure ("still exists after the delete"), `NOT_FOUND` prints `  NAME: NOT_FOUND`, any other error counts; nonzero at the end with one `ERROR:` line naming the count. Dispatcher: `retire-weekday-earnings) _PIN_AFTER=0; retire_weekday_earnings ;;`; add the label to the `_NEEDS_DEPLOY_CREDS=0` list (it reads no secret: `test_targets_that_read_no_secret_are_exempt_from_the_eager_probe` requires it); help: `retire-weekday-earnings  Delete daily-earnings-refresh-history and -reactions (one-shot; spec C Close-out step 4)`. A whole-script run under such a stub was exercised for this plan: exit 0 with six recorded calls, and exit 1 with a failing delete (run).
- [ ] **Step 4: Run** `bash -n gcp/deploy.sh`, then `python3 -m pytest tests/gcp/test_deploy_reachability.py tests/gcp/test_deploy_flag_syntax.py -q`, then the render step. Expected: PASS; renders unchanged.
- [ ] **Step 5: Commit** `feat(deploy): add a one-shot target that retires the weekday earnings entries`.

### Task 11: The three implementation-source notes and the source snapshot

Spec: frontmatter `site_source_notes: [CATALYSTS-01, CATALYSTS-04, DASHBOARD-01]`; § Design 7. Advances done_when[8]. Protocol: `.claude/skills/product-delivery/SKILL.md`, "Committed-source documentation identity".

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (the `## Implementation-source notes` table, `:1297`: two added rows, one extended)
- Modify: `docs/review-evidence/site-source-snapshot.json` (produced)

- [ ] **Step 1: Preflight** `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy the reported `source_identity_sha256`.
- [ ] **Step 2: The rows**, in sorted position (after the last FEAT-DATA-001 row, before `| FEAT-DEPLOY-001 | DASHBOARD-01 |`), each beginning `source_identity_sha256=<identity>; `:
  - `| FEAT-DEPLOY-001 | CATALYSTS-01 |`: `gcp/fetchers/compute_earnings_reactions.py` requests a ticker's AlphaVantage splits only for an event whose daily window it can check, stops its vendor requests after 3 consecutive or 10 request failures (`VendorRequestBudget`) and names every remaining ticker's events `split_status_unavailable`, and `gcp/deploy.sh` (`deploy_compute_earnings_reactions`) runs it under a 19,800 s timeout; the earnings history this element shows comes from those rows. Tests: `tests/gcp/test_compute_earnings_reactions.py` (`test_splits_requested_only_for_a_checkable_window`, `test_vendor_failures_stop_the_run`), `tests/gcp/test_deploy_reachability.py` (`test_compute_earnings_reactions_declares_its_sizing_on_both_branches`). Implementation source only: nothing is deployed until the owner's Close-out step 1.
  - `| FEAT-DEPLOY-001 | CATALYSTS-04 |`: on Sunday the views this element's timeline reads are refreshed by `earnings-sunday-chain` (`gcp/earnings_sunday_chain.py`, scheduled by `gcp/deploy.sh` at `30 19 * * 0`) after that evening's reaction execution completes, not before 20:00 ET. Tests: `tests/gcp/test_earnings_sunday_chain.py` (`test_consumers_start_after_the_reaction_execution`), `tests/gcp/test_deploy_reachability.py` (`test_sunday_chain_replaces_the_five_sunday_entries`). Implementation source only.
  - `| FEAT-DEPLOY-001 | DASHBOARD-01 |`, extended: the new identity and `the Sunday brief is started by earnings-sunday-chain at 21:00 ET or after the sweep completes, whichever is later, with BRIEF_TRIGGERED_BY=cloud-scheduler:earnings-sunday-chain; premarket-brief-sunday is no longer declared. Tests: ... Implementation source only.`, then ` Earlier: ` and the existing note's prose after its `source_identity_sha256=...; ` prefix, byte for byte.
  No other byte of the document changes. Commit `docs(site): spec C implementation-source notes for CATALYSTS-01, CATALYSTS-04 and DASHBOARD-01`.
- [ ] **Step 3: Produce** with the Step 1 command; commit `docs(evidence): site source snapshot for the bounded reaction run and the Sunday chain`.
- [ ] **Step 4: Verify** `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000`; expected exit 0 with `"status": "identity-matched"`. After any later commit that changes watched code, the document body or the policy (including #2057 merging), repeat Steps 1 to 4. If it refuses on size, stop and report the measured size; never raise a ceiling.

### Task 12: The Capacity numbers on the PR day

Spec: done_when[7]; § Design 8. Production reads only, each pasted with its read time.

- [ ] **Step 1: Ticker counts a run** (the command was run for this plan and returned the 27 runs above): `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="compute-earnings-reactions" AND textPayload:"tickers (after window-aware skip)"' --freshness=31d --limit=100 --format='value(timestamp,textPayload)'`.
- [ ] **Step 2: Durations:** `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs executions list --job=<job> --region=us-east1 --limit=60 --format='value(metadata.name,status.startTime,status.completionTime,status.succeededCount,status.failedCount)'` for `compute-earnings-reactions`, `earnings-long-watchlist`, `refresh-earnings-views`, `earnings-sweep` and `premarket-brief`; the Sunday executions of the four consumers give the chain's wall-clock.
- [ ] **Step 3: Write the PR body's Capacity section**: Volume, Velocity, Wall-clock and cost as above with the fresh numbers; the stop's failure bound in seconds (10 x 30.4 s = 304 s today, 604 s after r2); the chain's wall-clock at the measured consumer durations; the cost of a run and a month of the reaction job and of the chain.

### Task 13: Close

Spec: § Done when. Closes done_when[6] and [8], re-checks [0] to [5] and [7].

**Files:**
- Modify: `docs/product/02-FEATURE-CATALOG.md` (the FEAT-DEPLOY-001 record, `:538`: Status and Last reviewed only; line 36's "66 jobs, 65 schedulers" is the live fleet and is not edited)
- Modify: `docs/product/12-PR-ISSUE-TRACEABILITY.md` (the FEAT-DEPLOY-001 PR lineage line, `:318`)
- Modify: this plan (`pr`)

- [ ] **Catalog:** append to the Status cell `; spec C: the reaction run requests splits only for a checkable event, stops after 3 consecutive or 10 vendor request failures, is sized 19800 s on both deploy branches, the Sunday readers are chained by completion under earnings-sunday-chain and the weekday entries have a one-shot retire target ([#<PR>](https://github.com/TeneikaAskew/stocks/pull/<PR>), spec [#2082](https://github.com/TeneikaAskew/stocks/pull/2082)); deploy, scheduler swap and retirement are the owner's close-out`; Last reviewed to the day of the edit.
- [ ] **Traceability:** append ` · [#<PR>](https://github.com/TeneikaAskew/stocks/pull/<PR>) *remediation*` to `:318`; set this plan's `pr`.
- [ ] **Suites:** `bash -n gcp/deploy.sh`; `make test`; expected all pass (the scratch copy with Tasks 4 to 8's deploy and test edits, without the registry rows, failed only the three registry tests; run).
- [ ] **Docs audit:** `LC_ALL=C python3 scripts/maintenance/docs_audit.py | grep -E '^\s*\[P' | sed -E 's/:[0-9]+//g; s/^\s+//' | sort` on the branch and on `origin/main`; `comm -23 branch main` is empty.
- [ ] **Gate:** `python3 scripts/gate/spec_gate.py --pr origin/main`; ok.
- [ ] **#2083 and #2060:** comment on #2083 with the three tests of "How #2083 is handled" and that the end-to-end daily-series case is r2's; leave it open. Comment on #2060 that the fix is on the PR and the hold stays until Close-out step 1.
- [ ] **PR body:** the spec and this plan by path; each done_when item as a `- [ ]` line starting with its text, ticked with its evidence; the red then green record of each new test; the Capacity section (Task 12); `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN` (`docs/product/canvases.yml:53-55`, read); the changed cases that pinned a retired scheduler, each with the line it pinned: `tests/gcp/test_deploy_reachability.py:432` (`_UNCHANGED["premarket-brief-sunday"]`), `tests/scripts/test_doc_inventory.py:276-277` (`schedulers_live_only`, `schedulers_repo_only` with `earnings-sweep-sunday`), `tests/meta/test_stage_one_run_hours.py:60` and `:195-196` (`refresh-earnings-views-weekly`), `tests/meta/test_model_registry_consistency.py:419` (the 65 floor), and none in `tests/scripts/test_verify_docs_against_live.py` (its `LIVE` fixture at `:61` models a live state and does not read `gcp/deploy.sh`; it passed on the scratch copy, run); the two sizing cases `tests/scripts/test_doc_inventory.py:474` and `:499`; the owner's close-out steps below, as not done. Then mark the PR ready and follow CLAUDE.md 2.5.
- [ ] **After the merge**, on a `docs/` branch: this plan's `status: done`.

## Owner's close-out steps (not tasks; each on the owner's yes, after the merge)

From the spec's Close-out section; none runs from the PR and none is a done_when box. Every `gcloud` call is prefixed `env -u CLOUDSDK_AUTH_ACCESS_TOKEN`, from a checkout of `main`.

1. `./gcp/deploy.sh fetchers` (Decision 1). Read back `compute-earnings-reactions` (`timeoutSeconds: '19800'`, `maxRetries: 0`, `memory: 2Gi`, `cpu: '1'`, the build's digest; live today: generation 38, 1800 s, image `sha256:1ffd80ad...`) and `earnings-sunday-chain` (`timeoutSeconds: '18000'`, `maxRetries: 0`; live today: not found). The next weekday reaction run's `splits_unavailable=<n> of <m> tickers` line, and any `vendor_requests_stopped` line, go on #2060 with the hold lifted.
2. `./gcp/deploy.sh schedulers`. Read back `earnings-sunday-chain` (`30 19 * * 0`, `America/New_York`, `ENABLED`, target `earnings-sunday-chain:run`); the list holds none of the five and still holds the two weekday entries and the Sunday calendar and history entries. Run after step 1: before it, the deploy exits nonzero and leaves the five.
3. The first Sunday after step 2: each of the five executions starts after its predecessor's completion and at or after its time; the chain's log has five `step=` lines.
4. In the session of r2's Close-out step 1, after its `fetchers` deploy: `./gcp/deploy.sh retire-weekday-earnings`; both names NOT_FOUND, `daily-earnings-refresh-calendar` still ENABLED.
5. Close #2060 with steps 1 and 4; note on r2's implementation PR and #2047; on a `docs/` branch, this plan's `status: done` and the catalog's live counts.

## Choices this plan makes where the spec is open

1. **Pacing lives in the budget** (`call` sleeps before every request but the run's first), so r2's second request kind is paced and counted in one place.
2. **A refusal neither counts nor resets** the consecutive count (Design 2 says only a success resets).
3. **After the stop, the remaining tickers' windows are not read**, and they are counted in `splits_unavailable` as Design 2 says; the summary line can then read `splits_unavailable=10 of 5 tickers` (the denominator is requests made, done_when[0]).
4. **A ticker's held SPLITS failure refuses only its events that reach the split check**; events refused earlier keep their own reason (on main a failed ticker refused all its events `split_status_unavailable`).
5. **The chain polls the operation** (`op.done()` every 30 s) and reads the counts from `op.result()` or `op.metadata`, so the fake clock drives the waits; a consumer's wait ends at its task timeout plus 300 s, which keeps the worst case inside 18,000 s.
6. **The chain reads `GCP_PROJECT` and `GCP_REGION`** from its own `--set-env-vars` (the pattern of `gcp/deploy.sh:1235`), with no hardcoded fallback; it takes no `${ENV_STRING}` and no database secret.
7. **`_schedule_verified` reads back the time zone** for every caller (done_when[4] requires it; every live caller reads `America/New_York`).
8. **A chain run started after 22:30 ET** (a hand run with `--allow-any-day`) logs `reactions_unfinished` at once and starts the consumers without waiting: the spec's fixed end, applied as written.
9. **#2083's end-to-end case is left to r2** (above); the issue stays open.

## Not checked for this plan

- Whether `op.result()` raises on a failed execution, and whether `op.metadata.name` is set when `run_job` returns (no `google-cloud-run` in this sandbox; the fakes cover both shapes; Close-out step 3 reads it live).
- Whether `gcloud run jobs update` accepts `--service-account` (the spec asks for it on both branches; `tests/gcp/test_deploy_flag_syntax.py` checks env and secret syntax only).
- `doc_source_snapshot.py produce` on the feature branch, and `docs_audit.py` and `spec_gate.py --pr` against the built change (the registry refusal excepted, Checks in the PR body).
- The spec's estimates (1.4 s a SPLITS request, r2's 70-minute peak, list prices) were copied, not re-measured.
