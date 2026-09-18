# MODEL-EARN-001 — Earnings-reaction analytics

**Code:** `lib/earnings_reactions.py` (958 lines) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Experimental · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-17

> **Scope of this document.** It records what the code does, read from the source and
> its tests. This one's quintile thresholds carry the **most complete recorded derivation**
> in this directory — see [Rationale](#rationale).

## What it decides

A **playability score** per upcoming earnings event, a **quintile** and confidence label
derived from it, and an **archetype** tag. Consumed by the pre-market brief's playbook
section, the watchlist UI, and the weekly long-side watchlist job.

CLAUDE.md's "`lib/` is the shared backend spine" says every consumer should read this one
implementation. **One does not.** The daily `earnings_upcoming_with_history` rebuild in
`gcp/refresh_earnings_views.py` — the table `platform/api/routers/earnings.py:122` serves to
the watchlist UI — derives its archetype through its own `_derive_archetype` (`:312-336`,
called at `:245`) rather than `classify_archetype`. The two agree on the numeric cut-points
but not on missing data:

| Input state | `classify_archetype` (`lib/earnings_reactions.py`) | `_derive_archetype` (`gcp/refresh_earnings_views.py`) |
|---|---|---|
| `dir_consistency` missing, `reversal_rate >= 0.40` | `quiet` (`:481-482`) | **`reversal_play`** — `(dir_cons or 0) < 50` is true for `None` (`:334-335`) |
| `reversal_rate` missing, `dir_consistency >= 0.65`, bias beyond ±0.5 | `quiet` (`:481-482`) | **`bullish_trend` / `bearish_trend`** (`:329-333`) |
| `directional_bias` missing | trend branch skipped (`:489`) | `bias = ... or 0.0` (`:328`) — a Rule 3.7 `or 0` on a financial field; same result today, by accident |
| no lean row at all | `quiet` | `None` (`:322-323`) |

So a watchlist row can carry `reversal_play` for a name whose canonical archetype is
`quiet`, and the brief and the watchlist can disagree on the same ticker on the same
morning. No issue tracks this; recorded as DOC-24 in
[07 § Documentation coverage](../product/07-MODEL-REGISTRY.md#documentation-coverage-and-freshness).
This document does not change the job's behaviour — routing the refresh through
`classify_archetype` is a code change for a code PR.

## The formula (locked in Phase 0.5)

```
playability_score = move_magnitude_norm
                  × max(dir_consistency, 0.5 + 0.5 × reversal_rate)
                  × log(options_volume + 1)

move_magnitude_norm  = move_magnitude / typical_daily_return
typical_daily_return = median(|daily_return_pct|) over last 64 returns   <- not 60
```

**The normalizing window is 64 returns, not the 60 the parameter is named for.**
`query_typical_daily_return(tickers, window_days=60)` binds `window_size = window_days + 5`
(`lib/earnings_reactions.py:619`), keeps the **65** most recent daily bars per ticker
(`:599`), and computes returns with `LAG(close)` (`:606`). The oldest bar has no predecessor
inside the window, so `WHERE prev_close IS NOT NULL` (`:616`) drops exactly one: **65 bars in,
64 returns out**, with no trim back to 60 anywhere in the function. The median is taken over
all 64 (`:612-614`).

This is not cosmetic. The median is the divisor in `move_magnitude_norm` (`:199`), so the score
is linear in `1 / typical_daily_return`, and the score is bucketed by the **fixed** cut-points
`(15.7, 21.2, 28.2, 41.9)` below — four extra bars can move a name across a quintile boundary
and therefore across the sizing guidance. The default is what production runs:
`enrich_with_playability` passes `daily_return_window = 60` straight through (`:879-883`,
`:902`) and `gcp/premarket_brief.py:615-616` calls it with no argument.

The `+ 5` carries no comment. The function's own docstring says *"over the last `window_days`
trading days"* (`:576`), while the docstring of the consumer hedges with a tilde — *"median
|daily_return_pct| over last ~60 trading days"* (`:175`). The tilde is the closest thing to an
acknowledgement in the source. **Whether the `+ 5` was a deliberate buffer for a data gap or an
off-by-five is not recorded anywhere**, which is why it is filed rather than silently
documented as intended.

## Quintiles — and their measured hit rates

`_QUINTILE_BOUNDARIES = (15.7, 21.2, 28.2, 41.9)` at `lib/earnings_reactions.py:227`.

| Quintile | Score | Hit rate | Confidence label | Action |
|---|---|---|---|---|
| Q5 | `>= 41.9` | **58.9%** | 🔥 HIGH | size up |
| Q4 | `28.2–41.9` | 51.7% | ✅ SOLID | standard sizing |
| Q3 | `21.2–28.2` | 46.5% | 🟡 OK | small position only |
| Q2 | `15.7–21.2` | 42.9% | ❓ WEAK | paper / watch |
| Q1 | `< 15.7` | 34.8% | 🚫 SKIP | below baseline; routed to `low_conviction` and rendered as a compact line, not dropped (see below) |

Boundaries are midpoints between adjacent quintile-average scores, so a score landing
exactly on an average maps to that quintile.

**Q1 names are not dropped.** `gcp/premarket_brief.py:669-696` moves every Q1-scoring
survivor into a separate `low_conviction` list (`:684-685`) rather than discarding it — the
comment records why: silently dropping them *"hides whole-slate visibility"* and made
mega-caps *"vanish without a trace"*. The daily embed then renders them per BMO/AMC bucket
as one compact `⤷ Also reporting (lower conviction): TICK, TICK, …` line (`:2684`,
`:2732`) and counts them in the title (`:2690`), so the full slate stays visible without
giving a below-baseline name a playability row.

## Archetypes

Evaluated in order by `classify_archetype` (`lib/earnings_reactions.py:479-496`); the first
match wins.

| Archetype | Condition (numeric) | Action hint |
|---|---|---|
| `quiet` | `move_magnitude_pct < 1.5`, or magnitude / consistency / reversal missing | skip |
| `reversal_play` | `reversal_rate >= 0.40` **and** `dir_consistency < 0.50` | gap reversal play |
| `bullish_trend` | `dir_consistency >= 0.65` **and** `directional_bias_pct > 0.5` | bullish gap play |
| `bearish_trend` | `dir_consistency >= 0.65` **and** `directional_bias_pct < -0.5` | bearish gap play |
| `mixed` | anything that matches none of the above | low conviction |

Note `quiet` absorbs the missing-data case, so a `quiet` tag means *either* a genuinely small
move *or* absent inputs. Those are different situations and the archetype does not separate
them.

## Tunable knobs

All environment variables; defaults are the Phase 0.5 locked values.

| Variable | Default | Sane range |
|---|---|---|
| `BRIEF_REACTION_LOOKBACK_QUARTERS` | 12 | 4–20 |
| `BRIEF_CONDITIONAL_GAP_BAND_PCT` | 2.0 | 1.0–5.0 |
| `BRIEF_CONDITIONAL_THRESHOLD` | 0.75 | — |
| `BRIEF_CONDITIONAL_MIN_SAMPLE` | 3 | — |
| `BRIEF_REACTION_MIN_NQ` | 12 | — |
| `RECOMMEND_LONG_ONLY` | **`true` in production** | `true` / `false` |

**`RECOMMEND_LONG_ONLY` changes what the model recommends, and it is on.**
`gcp/deploy.sh:1061-1066` sets it `true` for the deployed job, read by
`lib/earnings_reactions.py:404-410`. With it on, `recommended_structure` never returns the
default iron condor: it returns a long straddle, long call or long put, and `SKIP` when the
implied move exceeds 15%. The deploy comment records the reason as an owner preference
(*"I would always buy them sell"*, 2026-05-22), not a measured result. An earlier revision
listed the knobs without it, so the document described a recommendation policy production
does not run.

## Entry points

`compute_playability_score` · `score_quintile` · `confidence_label` ·
`classify_archetype` · `recommended_structure` · `action_hint_for_archetype` ·
`select_earnings_winner` · `get_earnings_calibration` · `query_reaction_stats` ·
`query_typical_daily_return` · `query_conditional_reactions`

## Rationale

**RECORDED — the best-evidenced derivation among the seven, not the only one.** The
quintile boundaries are *"calibrated against the 21,592-prediction backtest
(`scripts/backtest_playability.py`, 2026-05-14)"*, and the per-quintile hit rates above
are quoted from that calibration. The monotonic 34.8% → 58.9% progression is what
justifies routing Q1 to the compact line and the size-up-at-Q5 guidance.

For comparison, [MODEL-MOM-001](MODEL-MOM-001.md) records a score-bucket walk-forward for
its floor of 5 and a 72.2% fire-rate measurement for dropping StochRSI, and
[MODEL-MR-001](MODEL-MR-001.md) records the 84.6% fire-rate that removed EMA proximity —
real derivations, but each covers a single change, and both models' operating bands remain
`UNKNOWN`. What is unique here is that the *whole* threshold set traces to one measured
backtest.

Two caveats a reader should carry:

1. The hit rates are **from the calibration backtest, not from live outcomes**. Nothing
   in this document claims they have held prospectively.
2. `scripts/calibrate_earnings.py` sweeps `(min_nq, lookback_quarters)` and
   `scripts/backtest_playability.py` is a walk-forward, so the machinery to re-measure
   exists — see CLAUDE.md Rule 3.5 rather than waiting for live data.

**The archetype cut-points are also recorded, and an earlier revision of this document
wrongly called them `UNKNOWN`.** `classify_archetype`'s docstring
(`lib/earnings_reactions.py:466-476`) gives both the numeric boundaries — reproduced in the
table above — and their provenance: *"Thresholds tuned against the 9-ticker case-study set"*,
listing the worked cases:

```
AVGO  -> bullish_trend (dir_cons 0.83, bias +3.24)
FDX   -> reversal_play (dir_cons 0.33, rev 0.50)
NVDA  -> mixed         (dir_cons 0.58, mid)
LLY   -> bullish_trend (dir_cons 0.67, bias +2.15)
JPM   -> mixed         (dir_cons 0.58)
WMT   -> bullish_trend (dir_cons 0.67, bias +1.06)
```

That is weaker evidence than the quintile calibration — nine tickers hand-checked, not a
21,592-prediction backtest — but it is a recorded derivation, and calling it `UNKNOWN`
discarded it. The error came from reading the *module* docstring and not the *function*
docstring; recorded as DOC-19 in
[07 § Documentation coverage](../product/07-MODEL-REGISTRY.md#documentation-coverage-and-freshness).

## Tests

`tests/lib/test_lib_earnings_reactions.py` · `test_conditional_lean.py` ·
`test_brief_two_track_redesign.py` · `tests/gcp/test_compute_earnings_reactions.py` ·
`test_earnings_reactions_brief.py` · `tests/scripts/test_calibrate_earnings.py`

## Known issues

[#863](https://github.com/TeneikaAskew/stocks/issues/863) winners posted to Discord at 99
days old. Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
