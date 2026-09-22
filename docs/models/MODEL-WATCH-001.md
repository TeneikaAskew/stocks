# MODEL-WATCH-001 — Long-side earnings watchlist ("Next NVAX")

**Code:** `gcp/earnings_long_watchlist.py` ·
**Reads:** `earnings_calendar`, `earnings_options_strategy_winners` ·
**Job:** `earnings-long-watchlist` (`45 19 * * 0`, Sunday evening) ·
**Output:** a Discord embed — no table ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Experimental · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-22

> Registered 2026-09-18, found by the round-10 scheduler sweep. It has no `lib/` import at
> all, which is exactly why the registry's old "imports `lib/` code" proxy never saw it.

## What it decides

Which upcoming earnings reporters are worth a **long-premium** look. One SQL statement
(`_query_watchlist`, `:115-176`) joins the next `days_ahead` days of `earnings_calendar`
against `earnings_options_strategy_winners`, keeps only the long structures, and ranks what
survives:

| Element | Value | Where |
|---|---|---|
| Look-ahead window | `CURRENT_DATE … CURRENT_DATE + :days_ahead`, default **7** days | `:150-151`, `--days` at `:322` |
| Structures kept | `long_straddle`, `long_strangle`, `long_call`, `long_put` | `:131-133` |
| Inclusion threshold | `COUNT(DISTINCT (structure, event_date)) >= :min_wins`, default **2** | `:169`, `--min-wins` at `:324` |
| Rank | prior wins DESC, then `MAX(pnl_pct)` DESC | `:170-171` |
| Cap | `LIMIT 25` | `:172` |

The decision is the **threshold plus the ranking**: a name with one prior win is not shown, a
name with three leads the post. Nothing downstream consumes it — the output is a Discord embed
read by a person, and there is no table behind it.

**Counting is by `(structure, event_date)` pair, not by event.** A ticker that won on both a
long straddle and a long call at the same earnings date counts **two**, and so clears the
default threshold on the strength of one event. Whether that is intended is not recorded; it is
what the `COUNT(DISTINCT (structure, event_date))` expression does.

## Freshness and failure behaviour — the part worth copying

This job is unusually disciplined about CLAUDE.md §3.7, and its comments say why in terms of
what went wrong:

- The winners snapshot must be at most `MAX_SOURCE_AGE_DAYS = 14` days old (`:68`,
  `_source_is_fresh` at `:107-113`) — "at most one missed weekly refresh". A missing or
  **future-dated** snapshot is rejected too.
- A failure of the freshness probe and a stale snapshot both suppress the post, and the code
  distinguishes them on purpose: *"'The probe could not run' and 'the snapshot is stale' both
  suppress the post, yet only the second is fixed by re-running the upstream fetcher"*
  (`:339-346`).
- The candidate query is not allowed to fail into an empty frame. The comment records the
  concrete failure it prevents: swallowed, *"this failure produced an empty frame that built a
  well-formed 'No candidate reporters this week.' post and exited 0 — a database outage
  published as a finding about the market"* (`:366-371`).

An empty result from a **healthy** query does still post, deliberately, so the cron's silence
is never ambiguous (`build_discord_message`, `:205-219`).

## Rationale

**UNKNOWN — not recorded in code or tests.** Neither `min_wins = 2`, the 7-day window, the
`LIMIT 25`, nor the choice to rank on prior win count rather than on any forward measure
carries a derivation. The premise is stated in the module docstring — *"Names that have blown
through implied move at earnings before are candidates to do it again"* — and stated is all it
is: no experiment in the ledger tests whether prior long-side winners repeat.

`MAX_SOURCE_AGE_DAYS = 14` is the one constant with a recorded reason (one missed weekly
refresh).

## Entry points

| Symbol | Role |
|---|---|
| `earnings_long_watchlist.main` (`:319`) | The scheduled entry point |
| `_query_watchlist` (`:115`) | The threshold and the ranking |
| `_source_is_fresh` (`:107`) | The staleness gate |

## Tests

`tests/gcp/test_earnings_long_watchlist_freshness.py` — **five test functions, nine cases**,
importing this module directly. It covers `_normalize_source_date` across `date`, `datetime`,
tz-aware `pd.Timestamp`, ISO string and `None`; a stale snapshot suppressing both the query and
the post; a fresh snapshot reaching the posting path; a failed freshness probe reported as
"cannot determine" rather than a missing snapshot; and a failed candidate query refusing to
post an empty watchlist.

**The SQL ranking itself is untested** — the `>= :min_wins` gate, the ordering and the
`LIMIT` carry no assertion. That is the real gap.

> Until 2026-09-22 this section read "No test file targets this module. The SQL carries the
> decision, so a test would need a real or fixture database; none exists." Both halves were
> wrong, and the second was refuted by the first: the suite monkeypatches
> `is_cloud_sql_configured`, `_latest_source_date`, `_query_watchlist` and
> `gcp.database.get_engine`, and needs no database. DOC-44.

## Known issues

**None filed.** The unevaluated premise above is the finding, and the `(structure, event_date)`
counting is recorded here rather than left to a reader of the Discord post.
