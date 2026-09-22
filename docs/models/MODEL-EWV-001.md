# MODEL-EWV-001 — Earnings Whispers strike verdicts

**Code:** `gcp/fetchers/evaluate_ew_strikes.py` ·
**Writes:** `earnings_calendar.ew_*` columns ·
**Job:** `evaluate-ew-strikes` (`0 23 * * 1-5`, after the close) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-22

> Registered 2026-09-18 by the round-10 sweep. It was invisible to the sweep's own first pass
> too: the audit script's write-detector matched `INSERT INTO` and `upsert_dataframe(...)` but
> not `UPDATE … SET`, which is the only way this job writes. It therefore reported
> "no write, no Discord, no lib/ import found" — evidence that would have justified excluding
> a job whose output a person reads every morning. The regex was fixed in the same change
> (`scripts/audit_scheduler_coverage.py`).

## What it decides

For each Earnings Whispers strike pick (`earnings_calendar` rows with
`data_source = 'earnings_whispers'` and a non-null `strike`), a **verdict on how the pick
played out** over the following regular session, plus the supporting measurements.

| Strategy | Verdict rule | Where |
|---|---|---|
| `Long Calls`, `Bull Spreads` | `HIT` if session `high >= strike`, else `MISS` | `:78-86` |
| `Long Puts`, `Bear Spreads` | `HIT` if session `low <= strike`, else `MISS` | `:87-95` |
| `Covered Calls` | `KEPT` if session `close <= strike`, else `ASSIGNED` | `:96-104` |
| Strangles, straddles, anything else | **no verdict** — the row is left NULL and skipped | `:106-108` |

Alongside the verdict it writes `ew_strike_move_pct` (signed, relative to the strike),
`ew_minutes_to_hit`, `ew_minutes_in_zone`, `ew_day_change_pct`, and the session high / low /
close.

This is a **measurement, not a prediction**: there is no threshold to derive and no edge to
validate. That is why it was registered `Production` / `KEEP` while every other system from
the round-10 sweep is `Experimental` — the question "did the underlying trade through the
strike" has one right answer.

**It has one right answer about one specific session, and for 53% of picks the job measures a
different one.** The arithmetic is correct and the input is wrong, which is why the status is
now `Production but needs remediation` / `RESTRUCTURE` rather than `KEEP`.

## Where the verdict goes

`gcp/premarket_brief.py` selects `ec.ew_strike_verdict, ec.ew_strike_move_pct` (`:358`), carries
it through `_first_non_null('ew_strike_verdict')` (`:509`) into the brief payload (`:544`), and
renders it at `:2391-2396` and `:2616` — gated, per the comment there, to *"only fire when
`ew_strike_verdict` is populated (post-eval)"*. So the verdict reaches a person through
[MODEL-BRIEF-001](MODEL-BRIEF-001.md). Nothing else in the repository reads these columns; no
router serves them.

## The session it scores is the wrong one for most picks

**53% of the scored verdicts in this table describe the session BEFORE the news.**

`evaluate_range` selects rows by `earnings_date` (`:155`), passes that same date to
`fetch_minute_data` (`:190`), and scores `09:30-15:59` of it. `earnings_time` — the column
that says whether the company reports before the open, after the close, or intraday — is
**never read**: it appears nowhere in the file. For an after-close reporter the announcement
lands *after* the session being measured, so the verdict answers "did the underlying trade
through the strike" about a session in which the market had not yet heard the news.

Measured against production on 2026-09-22:

| `earnings_time` | picks | with a verdict written |
|---|---:|---:|
| **`postmarket`** | **1,269** | **1,261** |
| `premarket` | 1,120 | 1,106 |
| `intraday` | 5 | 5 |

So **1,261 of 2,372 scored rows (53.2%)** are wrong-session. `premarket` is correct — the news
is out before 09:30, so the same day's session is the right one — and `intraday` is ambiguous
by nature. This is the majority of the surface, not a corner, and the verdicts are already
written and already rendered by the premarket brief.

Tracked as [#1151](https://github.com/TeneikaAskew/stocks/issues/1151). The fix is code:
resolve a `postmarket` row to the **next** trading session before fetching bars.

> **An earlier revision of this document called the session handling "right, and non-obviously
> so", and used that to justify `Production` / `KEEP`.** The reasoning it gave was sound as far
> as it went and is kept below, because it is still true and still worth knowing. It was simply
> the wrong thing to have been confident about: I verified the timezone of the window and never
> asked which day the window was on. Status is now `Production but needs remediation` /
> `RESTRUCTURE`.

### The timezone of the window is right, and that part is not obvious

`bars.between_time('09:30', '15:59')` (`:191`) filters on the index's **wall clock**, which is
only correct if the index is Eastern. It is: `fetch_minute_data` states *"Timestamps are
returned in naive ET (Eastern Time) as-is from AV"*
(`gcp/fetchers/fetch_market_data.py:62`), and this job calls AlphaVantage directly rather than
reading `market_data_intraday` — the table that, per CLAUDE.md §3.9, still holds two
conflicting conventions. A future change that swapped the source to that table would silently
break the window.

## Two real defects: an ambiguous skip, and a gap that never backfills

`fetch_minute_data` returns an **empty DataFrame** when the API key is missing
(`fetch_market_data.py:65-67`) — a §3.7 silent fallback in the fetcher. Downstream,
`_compute_verdict` returns all-`None` for empty bars (`:64-65`), the loop sees
`v['verdict'] is None` and executes `continue  # unsupported strategy or no bars` (`:196-197`).

The comment names both causes, and that is the problem: the two are not equivalent. A strangle
has no verdict by design and never will. A missing bar set is a **failure**, and the row is
simply left NULL.

> **It does not self-heal, and an earlier revision of this document said it did.** That claim
> came from reading `where_force = '' if force else 'AND ew_strike_verdict IS NULL'` (`:149`)
> and stopping there. The same query, six lines down, also binds
> `AND earnings_date BETWEEN :s AND :e` (`:155`, one line above where `{where_force}` is
> interpolated at `:156`) — and `main()` defaults that range to
> **yesterday alone**, walked back over weekends (`:230-236`):
>
> ```python
> y = date.today() - timedelta(days=1)
> while y.weekday() >= 5:
>     y -= timedelta(days=1)
> start = end = y
> ```
>
> So the NULL-verdict filter only ever re-offers rows from the one day the run is already
> looking at. A day whose bars failed to fetch is **never revisited** by any later scheduled
> run; its verdicts stay NULL indefinitely until somebody runs an explicit historical range:
>
> ```bash
> python -m gcp.fetchers.evaluate_ew_strikes --start 2026-09-15 --end 2026-09-15
> ```
>
> Nothing counts the outage, nothing logs it as distinct from a straddle, and nothing schedules
> that backfill — so the repair depends on a person noticing NULL verdicts in the premarket
> brief. Recorded here rather than fixed: the fix is a code PR.

`--force` re-evaluates rows already scored (`:149`), within whatever range it is given.

## Rationale

**Recorded, and it is short because there is little to derive.** The verdict rules follow from
the strategy's own payoff: a long call is in the money if the underlying traded at or above the
strike, a covered call is kept if it did not. The one judgement that is not forced is using the
session **high / low** for long structures and the **close** for covered calls; the docstring
states it (`:16-18`) without arguing it, and it matches how each position is actually resolved.

`minutes_to_hit` is measured from `reg_bars.index.min()` (`:117`, `:124`) — the first bar
**present**, not 09:30. On a session with missing early bars the figure is understated by the
gap.

## Entry points

| Symbol | Role |
|---|---|
| `evaluate_ew_strikes.evaluate_range` (`:134`) | The scheduled entry point; `--start` / `--end` / `--force` |
| `_compute_verdict` (`:51`) | The verdict and its supporting metrics |

## Tests

No test file targets this module. `_compute_verdict` is a pure function of
`(strategy, strike, bars)` and is the obvious unit-test surface; nothing exercises it.
`tests/gcp/test_premarket_brief.py:2387-2413` exercises the **consumer** with
`ew_strike_verdict='HIT'` and `None` fixtures, so the rendering is covered and the derivation
is not.

## Known issues

[#1151](https://github.com/TeneikaAskew/stocks/issues/1151) after-close reporters are scored
against the pre-announcement session — 1,261 of 2,372 scored rows, measured 2026-09-22.

Two further findings recorded here rather than filed: the ambiguous skip (a vendor outage and
an unsupported strategy take the same `continue`), and the day-gap that no scheduled run ever
revisits. The absent unit tests on `_compute_verdict` — a pure function and the obvious test
surface — are the third.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
