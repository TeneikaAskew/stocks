# MODEL-EWV-001 — Earnings Whispers strike verdicts

**Code:** `gcp/fetchers/evaluate_ew_strikes.py` ·
**Writes:** `earnings_calendar.ew_*` columns ·
**Job:** `evaluate-ew-strikes` (`0 23 * * 1-5`, after the close) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production · **Rec:** KEEP
**Doc health:** CURRENT · **Last verified:** 2026-09-18

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

This is a **measurement, not a prediction** — which is why the status is `Production` and the
recommendation `KEEP` while every other system registered in the round-10 sweep is
`Experimental`. There is no threshold to derive and no edge to validate: the question "did the
underlying trade through the strike" has one right answer, and the code computes it. What it
still needs is to be correct about the session, and that part is checkable.

## Where the verdict goes

`gcp/premarket_brief.py` selects `ec.ew_strike_verdict, ec.ew_strike_move_pct` (`:358`), carries
it through `_first_non_null('ew_strike_verdict')` (`:509`) into the brief payload (`:544`), and
renders it at `:2391-2396` and `:2616` — gated, per the comment there, to *"only fire when
`ew_strike_verdict` is populated (post-eval)"*. So the verdict reaches a person through
[MODEL-BRIEF-001](MODEL-BRIEF-001.md). Nothing else in the repository reads these columns; no
router serves them.

## The session window is right, and the reason is not obvious

`bars.between_time('09:30', '15:59')` (`:191`) filters on the index's **wall clock**, which is
only correct if the index is Eastern. It is: `fetch_minute_data` states *"Timestamps are
returned in naive ET (Eastern Time) as-is from AV"*
(`gcp/fetchers/fetch_market_data.py:62`), and this job calls AlphaVantage directly rather than
reading `market_data_intraday` — the table that, per CLAUDE.md §3.9, still holds two
conflicting conventions. A future change that swapped the source to that table would silently
break the window.

## One real defect: a vendor outage and an unsupported strategy are the same skip

`fetch_minute_data` returns an **empty DataFrame** when the API key is missing
(`fetch_market_data.py:65-67`) — a §3.7 silent fallback in the fetcher. Downstream,
`_compute_verdict` returns all-`None` for empty bars (`:64-65`), the loop sees
`v['verdict'] is None` and executes `continue  # unsupported strategy or no bars` (`:196-197`).

The comment names both causes, and that is the problem: the two are not equivalent. A strangle
has no verdict by design and never will. A missing bar set is a **failure** — the row stays
NULL, the next run re-selects it (the loop's default filter is
`AND ew_strike_verdict IS NULL`, `:149`), so it is self-healing, but nothing counts or logs the
outage, and a run in which every ticker failed to fetch exits the same way as a run in which
every pick was a straddle.

`--force` re-evaluates rows already scored (`:149`).

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

**None filed.** The ambiguous-skip finding above and the absent unit tests are recorded here.
