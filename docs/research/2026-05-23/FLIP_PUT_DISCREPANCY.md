# Live audit vs production-replay discrepancy: `gamma_flip_cross` PUT-aligned

**Status:** OPEN — needs reconciliation before relying on flip-cross signals in production
**Found during:** Phase 2 of the 2026-05-23 trading-hypothesis audit, when 10yr historical replay couldn't reproduce the 76.7% hit-rate that justified the flip-cross PUT direction-mapping in the codebase.

## The two numbers

| measurement | source | window | N | hit_15m | aligned hit_60m |
|---|---|---|---|---|---|
| **Live audit (76.7%)** | `docs/audits/gamma_proximity_2026-05-23.md`, line 176 | 30d (2026-04-13 → 2026-05-23) | **18 events** | **76.7%** | not reported |
| **10-year historical replay** | This audit (Phase 2), `gamma_events` table | 10 years (2016-05 → 2026-05) | **14 events total** | hit_15m = 33.3% (12 valid) | hit_60m = 25.0% |
| **30-day historical replay** (matching the live window exactly) | This audit, same data, filtered to 2026-04-13 → 2026-05-23 | 30d | **1 event** (QQQ 5/5/2026) | n/a (single event) | n/a |

The two should match if the live audit's logic and the production code's logic are the same. They don't.

## Replay path (this audit's measurement)

```
EOD chain (etf_options_snapshots, alphavantage source)
  → lib.gamma.build_summary()
  → gamma_levels_eod (flip_price stored per ticker × date)

intraday 1-min RTH bars (market_data_intraday_{spy,iwm,qqq})
  → for each bar:
      lib.strategies.gamma_proximity.evaluate_flip_cross(
        prev_close = prior bar's close,
        close = current bar's close,
        summary = built from PRIOR day's gamma_levels_eod row,
        prev_day_dir = from prior day's market_data_daily close vs open
      )
  → fires when:
      (prev_close <= flip < close) OR (prev_close >= flip > close)
      AND prev_day_dir is FTFC-aligned with the alert direction
```

This is **the exact same call path that `gcp/signal_monitor.py` uses in production live**. The dedup, the FTFC filter, the flip definition — all identical.

## Live audit path (what produced the 76.7%)

The audit doc (`docs/audits/gamma_proximity_2026-05-23.md` §"Event detection") says:
> **flip_cross**: bars where `(prev_close, close)` straddle the flip price

…which is the same straddle definition. But the actual SQL used was not committed (per line 30-33: *"Gate / flip × FTFC validation lives in the audit doc (the queries were dispatched ad-hoc via db-query.yml and aren't committed)"*).

Without the original SQL, we can't tell whether the 18-event count came from:
- A different flip-price computation (e.g. raw `etf_options_snapshots` aggregation differing from `lib.gamma.compute_gamma_flip`)
- A different straddle definition (e.g. "anywhere in the session price was above the flip then closed below", rather than strict bar-to-bar)
- A different FTFC alignment rule
- A different ticker / date set

## Bar-level cross counts in the 30d live window (this audit, SQL-direct)

To strip the Python layer out of the comparison, I ran the same straddle check directly in SQL against `gamma_levels_eod.flip_price` (the same flip my replay uses):

| ticker | prev_day_dir | n_cross_down | n_cross_up | n_unique_days_with_down_cross |
|---|---|---|---|---|
| SPY | DOWN | **0** | 0 | 0 |
| SPY | UP | 16 | 17 | 4 |
| IWM | DOWN | **0** | 0 | 0 |
| IWM | UP | 6 | 8 | 2 |
| QQQ | DOWN | **1** | 2 | 1 |
| QQQ | UP | 27 | 27 | 5 |

**PUT × FTFC-aligned (prev_day_dir=DOWN AND crossed down): 1 event total** across 3 tickers in 30 days.

**vs UP-prev-day × cross-down (NOT FTFC-aligned for PUT): 49 events** across 3 tickers in 30 days.

The 18 events the live audit reports as "PUT × aligned (DOWN)" can only come from a definition that's materially different from "(prev_close, close) straddle the prior-day flip AND prev_day_dir=DOWN".

## What this means for production

The production `lib.strategies.gamma_proximity.evaluate_flip_cross` (called by `gcp/signal_monitor.py`) fires alerts under the STRICT bar-to-bar straddle definition. In 10 years of historical data, we have:

- **94 total `gamma_flip_cross` events** (80 CALL, 14 PUT)
- **PUT × FTFC-aligned hit_15m = 33.3%** (n=12), nowhere near the live-audit 76.7%
- **Live signal_monitor is firing alerts at roughly 1 every 5-6 weeks for this kind**, not the much more frequent rate the live audit's data would suggest

The 76.7% figure was the empirical justification for the codebase's flip-PUT direction mapping (see comment in `lib/strategies/gamma_proximity.py:23-29`). **If the live audit's measurement was based on a different alert detection than what `evaluate_flip_cross` actually does, the direction mapping is supported by a number that doesn't apply to what the live system fires.**

This is not a "bug we need to roll back" — the direction mapping might still be the right call. But the **empirical support for it should be re-established** using the production code path, over a long enough window to have meaningful N.

## Recommended remediation

1. **Find the original audit SQL.** Check the run IDs in `gamma_proximity_2026-05-23.md` (`26323951771`, `26324343479`, `26324741563`) for the actual flip-cross queries. GitHub Actions retention may have expired (90 days default). If retrievable, diff against `lib.strategies.gamma_proximity.evaluate_flip_cross`.
2. **If irretrievable**, run a fresh production-replay AS-OF the same 30-day window using `scripts/replay_signal_monitor.py` (the canonical hermetic replay path per CLAUDE.md Rule 3.6). Compare its alert counts to what the live `signal_monitor` actually fired during that window (`signal_alerts` table for the same dates).
3. **Either** confirm the production code is identical to what produced 76.7%, **or** establish the actual hit-rate of production's `evaluate_flip_cross` over a window with meaningful N (probably 2-3 years post the change).
4. **Until the discrepancy is reconciled**, treat `gamma_flip_cross` alerts as unvalidated. Don't size up on them. The flip mapping might be right; the 76.7% number is not currently the right evidence.

## Why I'm filing this here, not as an issue

This is a research finding from the 2026-05-23 audit, not a production incident. The signal_monitor is firing the alerts it's wired to fire; nothing is broken. The audit's job is exactly this: pressure-test whether the empirical numbers in the documentation match the production code path. This one doesn't match, and the doc is the source of truth for the direction mapping that ships in `evaluate_flip_cross`. Worth flagging plainly so the next PR that touches flip-cross either fixes the evidence or fixes the code.
