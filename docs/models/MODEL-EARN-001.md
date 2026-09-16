# MODEL-EARN-001 — Earnings-reaction analytics

**Code:** `lib/earnings_reactions.py` (958 lines) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Experimental · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Unlike the other models in this directory, **this one's thresholds carry a
> recorded derivation** — see [Rationale](#rationale).

## What it decides

A **playability score** per upcoming earnings event, a **quintile** and confidence label
derived from it, and an **archetype** tag. Consumed by the pre-market brief's playbook
section, the watchlist UI, and the weekly long-side watchlist job.

Per CLAUDE.md's "`lib/` is the shared backend spine", every consumer reads this one
implementation rather than reimplementing the formula.

## The formula (locked in Phase 0.5)

```
playability_score = move_magnitude_norm
                  × max(dir_consistency, 0.5 + 0.5 × reversal_rate)
                  × log(options_volume + 1)

move_magnitude_norm  = move_magnitude / typical_daily_return
typical_daily_return = median(|daily_return_pct|) over last 60d
```

## Quintiles — and their measured hit rates

`_QUINTILE_BOUNDARIES = (15.7, 21.2, 28.2, 41.9)` at `lib/earnings_reactions.py:227`.

| Quintile | Score | Hit rate | Confidence label | Action |
|---|---|---|---|---|
| Q5 | `>= 41.9` | **58.9%** | 🔥 HIGH | size up |
| Q4 | `28.2–41.9` | 51.7% | ✅ SOLID | standard sizing |
| Q3 | `21.2–28.2` | 46.5% | 🟡 OK | small position only |
| Q2 | `15.7–21.2` | 42.9% | ❓ WEAK | paper / watch |
| Q1 | `< 15.7` | 34.8% | 🚫 SKIP | below baseline; the brief drops these rows |

Boundaries are midpoints between adjacent quintile-average scores, so a score landing
exactly on an average maps to that quintile.

## Archetypes

| Archetype | Condition | Action hint |
|---|---|---|
| `bullish_trend` | high `dir_consistency`, positive `directional_bias` | bullish gap play |
| `bearish_trend` | high `dir_consistency`, negative `directional_bias` | bearish gap play |
| `reversal_play` | high `reversal_rate`, low `dir_consistency` | gap reversal play |
| `mixed` | moderate on both axes | low conviction |
| `quiet` | small `move_magnitude` or no clear pattern | skip |

## Tunable knobs

All environment variables; defaults are the Phase 0.5 locked values.

| Variable | Default | Sane range |
|---|---|---|
| `BRIEF_REACTION_LOOKBACK_QUARTERS` | 12 | 4–20 |
| `BRIEF_CONDITIONAL_GAP_BAND_PCT` | 2.0 | 1.0–5.0 |
| `BRIEF_CONDITIONAL_THRESHOLD` | 0.75 | — |
| `BRIEF_CONDITIONAL_MIN_SAMPLE` | 3 | — |
| `BRIEF_REACTION_MIN_NQ` | 12 | — |

## Entry points

`compute_playability_score` · `score_quintile` · `confidence_label` ·
`classify_archetype` · `recommended_structure` · `action_hint_for_archetype` ·
`select_earnings_winner` · `get_earnings_calibration` · `query_reaction_stats` ·
`query_typical_daily_return` · `query_conditional_reactions`

## Rationale

**RECORDED — the only one of the seven with a derivation in source.** The quintile
boundaries are *"calibrated against the 21,592-prediction backtest
(`scripts/backtest_playability.py`, 2026-05-14)"*, and the per-quintile hit rates above
are quoted from that calibration. The monotonic 34.8% → 58.9% progression is what
justifies the Q1-drop and the size-up-at-Q5 guidance.

Two caveats a reader should carry:

1. The hit rates are **from the calibration backtest, not from live outcomes**. Nothing
   in this document claims they have held prospectively.
2. `scripts/calibrate_earnings.py` sweeps `(min_nq, lookback_quarters)` and
   `scripts/backtest_playability.py` is a walk-forward, so the machinery to re-measure
   exists — see CLAUDE.md Rule 3.5 rather than waiting for live data.

The archetype cut-points ("high", "low", "moderate" `dir_consistency`) are **UNKNOWN** —
the source names the bands but does not give their numeric boundaries or derivation.

## Tests

`tests/lib/test_lib_earnings_reactions.py` · `test_conditional_lean.py` ·
`test_brief_two_track_redesign.py` · `tests/gcp/test_compute_earnings_reactions.py` ·
`test_earnings_reactions_brief.py` · `tests/scripts/test_calibrate_earnings.py`

## Known issues

[#863](https://github.com/TeneikaAskew/stocks/issues/863) winners posted to Discord at 99
days old. Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
