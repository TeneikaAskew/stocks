# MODEL-EWV-001 — Earnings Whispers strike verdicts

**Last reviewed:** unknown · **Last scanned:** 2026-11-03 · **Owner:** TBD

**Code:** `gcp/fetchers/evaluate_ew_strikes.py` ·
**Writes:** none; historical `earnings_calendar.ew_*` columns retained ·
**Job:** retired `evaluate-ew-strikes`; only the shared NYSE shim remains ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Retired (operationally, 2026-11-13) · **Rec:** REMOVE
**Doc health:** CURRENT · **Last verified:** 2026-09-26

> Registered 2026-09-18 by the round-10 sweep. It was invisible to the sweep's own first pass
> too: the audit script's write-detector matched `INSERT INTO` and `upsert_dataframe(...)` but
> not `UPDATE … SET`, which is the only way this job writes. It therefore reported
> "no write, no Discord, no lib/ import found" — evidence that would have justified excluding
> a job whose output a person reads every morning. The regex was fixed in the same change
> (`scripts/audit_scheduler_coverage.py`).

## Operational retirement — 2026-11-13

The evaluator Cloud Run job and Scheduler are removed. The separately deployed
premarket brief no longer consumes or renders EW picks or verdicts. Its verified
execution `premarket-brief-s7kz6` completed at 15:32:06 UTC on November 13, retaining
non-EW earnings, prior-AMC reactions, market analysis and economic-calendar output.
Historical rows and verdict columns remain intact.

This source change removes the scorer implementation from
`gcp/fetchers/evaluate_ew_strikes.py`; it introduces no new deployment claim. The existing
`nyse_sessions` helper and its AV collector and earnings-session consumers remain
required. No calendar, schema, secret or historical data is removed here.

The scorer behavior and incident measurements below are retained historical
context; they do not assert that the retired scheduled scorer is still running.

## Source and test retirement

Executed collection at d806bfd1 recorded 71 cases over 35 functions: 49 scorer
cases are retired and 22 vendor cases are moved verbatim. Fresh implementation
base 6e04eb53 independently collects the same 71 cases. Five new shim cases
replace no vendor or consumer assertion. Repository collection changes from
9,629 to 9,585 cases, exactly minus 49 plus 5; other files retain their counts.

## What it decided (historical)

For each Earnings Whispers strike pick (`earnings_calendar` rows with
`data_source = 'earnings_whispers'` and a non-null `strike`), a **verdict on how the pick
played out** over the session its news reaches, plus the supporting measurements.

| Strategy | Verdict rule | Where |
|---|---|---|
| `Long Calls`, `Bull Spreads` | `HIT` if session `high >= strike`, else `MISS` | `:117-125` |
| `Long Puts`, `Bear Spreads` | `HIT` if session `low <= strike`, else `MISS` | `:127-134` |
| `Covered Calls` | `KEPT` if session `close <= strike`, else `ASSIGNED` | `:136-145` |
| Strangles, straddles, anything else | **no verdict**, counted as `no_verdict` | `:147-149` |

Alongside the verdict it writes `ew_strike_move_pct` (signed, relative to the strike),
`ew_minutes_to_hit`, `ew_minutes_in_zone`, `ew_day_change_pct`, and the session high / low /
close. Production picks use two strategies, Covered Calls (1,788) and Long Calls (615), both
supported (measured 2026-09-24).

This is a **measurement, not a prediction**: there is no threshold to derive and no edge to
validate. The question "did the underlying trade through the strike" has one right answer,
**about one specific session**, and until #1151 the job measured the wrong one for more than
half the picks.

## Where the verdict goes

**The premarket brief no longer consumes or renders EW picks or verdicts.** The
FEAT-PLAYBOOK-001 retirement excludes both retired source aliases before its two
loader calculations and removes recap acquisition, including historical replays.
Compatibility strategy/strike/premium/score fields remain empty. Historical
calendar verdicts and this evaluator's audit evidence remain intact; this source
change makes no deployment claim.

Historical context: #1168 introduced a weekday recap of the last NYSE session,
using the evaluator's scoring-session rule. Before that fix, today's verdict
could leak into a historical morning replay even though the live 08:30 brief
preceded scoring at 23:00 ET. Earlier revisions and #1151 incorrectly described
those verdicts as already rendered to a person. #1168 subsequently covered
Monday/Friday session selection, after-close picks, empty days, visible load
failures and NULL minute metrics. Those receipts describe the old consumer;
retirement does not undo the evaluator's historical session-correctness work.

Current brief tests in `tests/gcp/test_premarket_brief.py` separately prove actual
SQL exclusion (`test_retired_sources_excluded_by_real_brief_sql` and
`test_retired_sources_excluded_by_real_prior_amc_sql`), no caller acquisition
(`test_brief_pipeline_never_acquires_ew_recap`) and ignored legacy payloads
(`test_legacy_ew_payload_cannot_render`, `test_legacy_nan_recap_metrics_are_ignored`).
The exact base/head node mapping preserves independent non-EW assertions. Ignoring
retired NaN metrics is source retirement evidence, not finite-value repair proof.

## The scoring session (#1151, closed 2026-09-26)

**Until #1151 the job scored every pick against the session of `earnings_date` itself.** It
selected rows by `earnings_date`, fetched that same date's bars and scored `09:30-15:59` of it;
`earnings_time` was never read. For an after-close reporter that is the session **before** the
news. Measured 2026-09-24: **1,263 of 2,383 scored verdicts (53.0%)** were after-close picks
scored against the pre-announcement session. The arithmetic was right and the input was not.

**Each pick is now scored against the session its news reaches**, resolved by
`scoring_session` (`:198-223`) from the NYSE calendar (`nyse_sessions`, `:186-195`):

| `earnings_time` | Scoring session |
|---|---|
| `postmarket` | the first NYSE session **after** `earnings_date` (a Friday report is Monday's; the Wednesday before Thanksgiving is Friday's) |
| `premarket` | the first session **on or after** `earnings_date` (a pick dated on a holiday is the next session's) |
| `intraday` | `earnings_date`'s own session. The news lands inside it, and scoring the whole session is the stated choice. No session that day means no verdict |
| anything else | no session; counted `unknown_timing`, never defaulted |

`pandas_market_calendars` is a hard dependency with no weekday fallback, since a guessed
session is exactly the defect. The bar window is the session's calendar open to close, so an
early close (13:00 ET on 2026-11-27 and 2026-12-24) ends the window there and after-hours bars
never count. A pick whose session has not closed yet is counted `pending_session` and left for a
later run: at 23:00 ET on the report day, an after-close pick's session is tomorrow.

The window's **timezone** was, and still is, right, and that part is not obvious.
`fetch_minute_bars` returns bars in *"naive ET (Eastern Time) as-is from AV"*
(`gcp/fetchers/fetch_market_data.py:83`), and the session bounds are converted to naive ET
before slicing. The job calls AlphaVantage directly rather than reading `market_data_intraday`,
the table that per CLAUDE.md §3.9 still holds two conflicting conventions; a change that swapped
the source to that table would silently break the window.

The evaluator fetches **as-traded** bars (`adjusted=False`), because a strike is quoted in the
prices of its day. A re-score months later against split-adjusted history would compare
different units.

### Re-scored 2026-09-26

After the fix was deployed, every after-close pick from 2026-04-20 to 2026-09-25 was re-scored
with `--force` in monthly chunks: 1,267 picks over 1,178 vendor calls, none empty and none
cleared (executions `evaluate-ew-strikes-j8jpt`, `-f774k`, `-66wbv`, `-9prnj`, `-hdx6q`,
`-9mhpt`). Measured against a snapshot taken before the deploy:

| after-close picks with both daily closes | before | after |
|---|---:|---:|
| stored close nearer the report day's close | 1,226 of 1,249 | 10 of 1,251 |
| stored close nearer the next session's close | 12 | 1,233 |
| median error against the next session's close | 5.1% | 0.040% |

- **The ten that still lean to the report day** are stocks whose two closes differ by 0.3% or
  less, plus AERO. AERO's session traded in only 168 minutes and last traded at 15.33, against an
  official close of 15.65.
- **328 of the 1,263 re-scored verdicts flipped (26%):** KEPT to ASSIGNED 183, ASSIGNED to KEPT
  92, HIT to MISS 37, MISS to HIT 16.
- **Four picks were scored for the first time**, including the two dated Memorial Day.
- **Before-open and intraday verdicts were not touched.**
- **Three spot checks matched exactly:** the stored high, low and close equal a by-hand
  recomputation from AlphaVantage bars.

Five before-open picks stay unscored, because AlphaVantage rejects the symbol or has no bars for
the day: TGEN, VSCO, MOG.A, ORLA and BF.B.

## Gaps now heal, and an outage is counted, not skipped

Two further defects were fixed with #1151:

- **A missed day was never revisited.** The default run scored one day, `date.today() - 1` on the
  container's UTC clock, which at 23:00 ET is the ET report day. A day whose bars failed to fetch
  stayed NULL until someone re-ran it by hand. The default is now a
  `DEFAULT_LOOKBACK_DAYS = 7` window (`:75`) over **unscored** rows only
  (`ew_strike_verdict IS NULL`, `:349`), so each night retries the week.
- **An outage and an unsupported strategy took the same silent `continue`.** Each is now its own
  counter: `no_bars` (the vendor had no bars for the pick) and `no_verdict` (no rule for the
  strategy). A missing `ALPHA_VANTAGE_API_KEY` raises (`:340`) instead of returning 0 rows and
  exiting 0.

`--force` re-scores rows already scored. A row the vendor answered for without bars is
**cleared** to NULL for the nightly run to fill, never left holding a verdict from the wrong
session. `--earnings-time` narrows a run to one timing, and `--dry-run` scores and logs without
writing.

## An outage is told from picks without bars (#1181)

Counting empty calls could not tell a vendor outage from picks the vendor has no bars for.
`fetch_minute_data` returned the same empty frame for a refused symbol, a rate limit, a transport
error and a day without bars. On 2026-09-26 a fill pass whose five calls were four refused
symbols and one day without bars exited 1 on both attempts and opened #1180.

- **Each call says why it is empty.** `fetch_market_data.fetch_minute_bars` returns
  `(bars, reason)`, with the reasons `fetch_alphavantage_intraday` already names.
  `fetch_minute_data` is that without the reason, so the daily fetcher and the premarket refresh
  read what they read before. The evaluator counts each empty call:
  - `unsupported_symbol`: `Error Message`
  - `rate_limited`: `Note` or `Information`
  - `transport_error`: a request error, or a reply without a time series

  A refused symbol or a day without bars is an answer about the pick (`no_bars`). The rest are
  not (`fetch_failed`): the pick is left as it was, and the next run's lookback retries it.
- **One SPY call decides a run whose every call came back empty** (`run_failures`, `:256-275`).
  It fetches SPY for the latest session fetched. Bars mean the vendor answers and the empty calls
  were about the picks, so the run exits 0. None means an outage or a broken request, so it
  exits 1. A night's only call is decided the same way; before, it could never fail the run
  (16 of 110 sessions from 2026-04-20 to 2026-09-24 had no fresh pick to fetch). A night where any
  call returned bars makes no SPY call.
- **`--force` clears a verdict only on an answer about the pick, and only once the vendor has
  answered.** A rate limit or a transport error keeps the stored verdict, and the run exits 1,
  because a partial re-score must not read as a complete one. A refusal or a day without bars
  clears it. Those clears are held to the end of the run, and are written only if some call or
  the SPY call returned bars, because AlphaVantage refuses a bad API key with the same
  `Error Message` as an unknown symbol. The code before this cleared every verdict on any empty
  call.
- **Share classes are sent dashed.** Earnings Whispers writes `BF.B` and `MOG.A`; AlphaVantage
  lists `BF-B` and `MOG-A` (SYMBOL_SEARCH, 2026-09-26). `av_listed_symbol` sends that form, and
  only this job uses it. The daily fetcher still sends the dotted form, which AlphaVantage
  refuses, so it stores no bars for any share class
  ([#1188](https://github.com/TeneikaAskew/stocks/issues/1188)).

The job makes one vendor call per (ticker, session), paced by `lib/config.py`'s AlphaVantage
plan limit. A call measured 1.1 to 1.4 s on 2026-09-25 and 26, most of it spent downloading a month
of 1-minute bars. So the job runs at roughly 45 to 55 calls a minute, well under the plan's 150,
and a nightly run of about 45 calls takes about 90 s. It writes one transaction per session date, so a long re-score keeps its progress
if it stops part way.

## Rationale

**Recorded, and it is short because there is little to derive.** The verdict rules follow from
the strategy's own payoff: a long call is in the money if the underlying traded at or above the
strike, a covered call is kept if it did not. The one judgement that is not forced is using the
session **high / low** for long structures and the **close** for covered calls; the docstring
states it (`:16-18`) without arguing it, and it matches how each position is actually resolved.

`minutes_to_hit` is measured from `reg_bars.index.min()` (`:168`, `:175`), the first bar
**present**, not 09:30. On a session with missing early bars the figure is understated by the
gap.

## Historical entry points

| Symbol | Role |
|---|---|
| `evaluate_ew_strikes.evaluate_range` (`:310`) | The scheduled entry point; `--start` / `--end` / `--lookback-days` / `--force` / `--earnings-time` / `--dry-run` |
| `scoring_session` (`:208-233`) | Which session a pick is scored against |
| `_compute_verdict` (`:101`) | The verdict and its supporting metrics |
| `run_failures` (`:256-275`) | Why the run exits 1: an empty SPY call after every call came back empty, or a `--force` pick with no answer |
| `fetch_market_data.fetch_minute_bars` / `av_listed_symbol` | The bars and the vendor's reason; the share-class symbol AlphaVantage lists |

## Tests

`tests/gcp/test_nyse_sessions_shim.py` contains five new tests for the retained
module: Thanksgiving absence, early close, DST open, missing-library error,
removed scorer exports and byte-identical wrapper source.
`tests/gcp/test_av_options_collector_entry.py` remains unchanged and exercises
the live caller's existing `ew.nyse_sessions` patch boundary.

The seven vendor functions and their helpers moved verbatim to the dedicated
vendor-answer suite, with all 22 parametrized cases retained. The separate
node-disposition receipt records every old/new node and the 49 retired scorer
cases. Finite-values repair obligations and historical results remain separate.

### Historical evaluator test evidence

The former evaluator test module was earlier described as **62 tests** covering
several areas. That historical count predates the executed 71-case inventory
above; the following incident evidence is preserved.
- **Sessions.** The scoring session for every timing, including the Friday, Thanksgiving and
  Memorial Day cases, and the 13:00 early close.
- **Verdicts.** The first tests of `_compute_verdict`.
- **The job's shape.** Four picks over two (ticker, session) pairs make exactly two fetches,
  bars are fetched as-traded, and there is one transaction per session date.
- **Failure modes.** A pending session is not fetched, a dry run writes nothing, a missing key
  raises, and a NULL timing that pandas returns as NaN is counted rather than crashing.
- **The vendor's answer (#1181).**
  - The wp7kf night exits 0, with the SPY call on the latest session fetched.
  - Each reply is counted by what it says.
  - Every call empty, plus an empty SPY call, exits 1 for a rate limit, a refusal or a transport
    error alike.
  - A rate-limited night whose SPY call has bars exits 0 and writes nothing.
  - No SPY call is made when any call returned bars.
  - A lone empty call is decided by the SPY call.
  - Two picks on one ticker are one call.
  - A share class is requested dashed.
  - `--force` keeps a verdict it got no answer for, clears nothing on refusals until the vendor
    has answered, and writes its held clears in one transaction after the updates.
  - `fetch_minute_bars` names each AlphaVantage reply, and `fetch_minute_data` keeps its contract.

Run against the code before #1181, 37 of the 62 failed. The wp7kf night's case read
`assert 1 == 0`: the old rule failed it. Run against the code before #1151, 26 of the 33 then in
the file failed. The case that is #1151 itself read
`assert ['2026-09-24'] == ['2026-09-25']`: the pre-announcement session was fetched.
The consumer's tests are with the consumer; see *Where the verdict goes*.

## Known issues

Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
