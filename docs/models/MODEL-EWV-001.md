# MODEL-EWV-001 — Earnings Whispers strike verdicts

**Code:** `gcp/fetchers/evaluate_ew_strikes.py` ·
**Writes:** `earnings_calendar.ew_*` columns ·
**Job:** `evaluate-ew-strikes` (`0 23 * * 1-5`, after the close) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-25

> Registered 2026-09-18 by the round-10 sweep. It was invisible to the sweep's own first pass
> too: the audit script's write-detector matched `INSERT INTO` and `upsert_dataframe(...)` but
> not `UPDATE … SET`, which is the only way this job writes. It therefore reported
> "no write, no Discord, no lib/ import found" — evidence that would have justified excluding
> a job whose output a person reads every morning. The regex was fixed in the same change
> (`scripts/audit_scheduler_coverage.py`).

## What it decides

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

`gcp/premarket_brief.py` selects `ec.ew_strike_verdict, ec.ew_strike_move_pct` (`:358`), carries
it through `_first_non_null('ew_strike_verdict')` (`:509`) into the brief payload (`:544`), and
renders it at `:2391-2396` and `:2616`. Nothing else in the repository reads these columns; no
router serves them.

**On the code path, the live brief never shows a verdict** (#1168). The brief loads the rows
whose `earnings_date` is today (in daily mode; the coming week on Sundays), at 08:30 ET, and this
job scores at 23:00 ET, so those rows are always unscored when read. The render path is reachable
only in `BRIEF_AS_OF` replays. This is from reading the code, not from a replay; #1168 names the
check that would confirm it. Earlier revisions of this document and #1151 said the verdicts were
"already rendered to a person"; on this reading they were not.

## The scoring session ([#1151](https://github.com/TeneikaAskew/stocks/issues/1151))

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
`fetch_minute_data` returns *"naive ET (Eastern Time) as-is from AV"*
(`gcp/fetchers/fetch_market_data.py:62`), and the session bounds are converted to naive ET
before slicing. The job calls AlphaVantage directly rather than reading `market_data_intraday`,
the table that per CLAUDE.md §3.9 still holds two conflicting conventions; a change that swapped
the source to that table would silently break the window.

The evaluator fetches **as-traded** bars (`adjusted=False`), because a strike is quoted in the
prices of its day. A re-score months later against split-adjusted history would compare
different units.

## Gaps now heal, and an outage is counted, not skipped

Two further defects were fixed with #1151:

- **A missed day was never revisited.** The default run scored one day, `date.today() - 1` on the
  container's UTC clock, which at 23:00 ET is the ET report day. A day whose bars failed to fetch
  stayed NULL until someone re-ran it by hand. The default is now a
  `DEFAULT_LOOKBACK_DAYS = 7` window (`:71`) over **unscored** rows only
  (`ew_strike_verdict IS NULL`, `:312`), so each night retries the week.
- **An outage and an unsupported strategy took the same silent `continue`.** Each is now its own
  counter: `no_bars` (the vendor returned nothing) and `no_verdict` (no rule for the strategy).
  A run where at least two vendor calls were made and none returned bars exits 1
  (`run_failed`, `:246-251`), and a missing `ALPHA_VANTAGE_API_KEY` raises (`:303`) instead of
  returning 0 rows and exiting 0. One empty call does not fail the run: it cannot tell an outage
  from a symbol the vendor lacks, and on a quiet night it is often the only call (16 of 110
  sessions from 2026-04-20 to 2026-09-24 had no fresh pick to fetch). It is counted, and retried
  while the pick is inside the lookback.

`--force` re-scores rows already scored. A row it cannot recompute is **cleared** to NULL for the
nightly run to fill, never left holding a verdict from the wrong session. `--earnings-time`
narrows a run to one timing, and `--dry-run` scores and logs without writing.

The job makes one vendor call per (ticker, session), paced by `lib/config.py`'s AlphaVantage
plan limit. It writes one transaction per session date, so a long re-score keeps its progress
if it stops part way.

## Rationale

**Recorded, and it is short because there is little to derive.** The verdict rules follow from
the strategy's own payoff: a long call is in the money if the underlying traded at or above the
strike, a covered call is kept if it did not. The one judgement that is not forced is using the
session **high / low** for long structures and the **close** for covered calls; the docstring
states it (`:16-18`) without arguing it, and it matches how each position is actually resolved.

`minutes_to_hit` is measured from `reg_bars.index.min()` (`:158`, `:165`), the first bar
**present**, not 09:30. On a session with missing early bars the figure is understated by the
gap.

## Entry points

| Symbol | Role |
|---|---|
| `evaluate_ew_strikes.evaluate_range` (`:286`) | The scheduled entry point; `--start` / `--end` / `--lookback-days` / `--force` / `--earnings-time` / `--dry-run` |
| `scoring_session` (`:198-223`) | Which session a pick is scored against |
| `_compute_verdict` (`:91`) | The verdict and its supporting metrics |

## Tests

`tests/gcp/test_evaluate_ew_strikes.py`: **33 tests** covering several areas.
- **Sessions.** The scoring session for every timing, including the Friday, Thanksgiving and
  Memorial Day cases, and the 13:00 early close.
- **Verdicts.** The first tests of `_compute_verdict`.
- **The job's shape.** Four picks over two (ticker, session) pairs make exactly two fetches,
  bars are fetched as-traded, and there is one transaction per session date.
- **Failure modes.** A pending session is not fetched, `--force` clears what it cannot re-score,
  a dry run writes nothing, a missing key raises, an all-empty run fails while one missing
  ticker or a lone empty call does not, the outage rule counts vendor calls rather than picks,
  and a NULL timing that pandas returns as NaN is counted rather than crashing.

Run against the code before #1151, 26 of them failed. The case that is #1151 itself read
`assert ['2026-09-24'] == ['2026-09-25']`: the pre-announcement session was fetched.
`tests/gcp/test_premarket_brief.py:2387-2413` still covers the **consumer** with
`ew_strike_verdict='HIT'` and `None` fixtures.

## Known issues

[#1151](https://github.com/TeneikaAskew/stocks/issues/1151) after-close reporters were scored
against the pre-announcement session (1,263 of 2,383 scored rows, measured 2026-09-24). Fixed in
code; stays open until the stored verdicts are re-scored against the right session.

[#1168](https://github.com/TeneikaAskew/stocks/issues/1168) the live premarket brief never shows
a verdict; only `BRIEF_AS_OF` replays do.

Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
