# Timeframe Heuristic — Empirical Analysis

**Date:** 2026-05-02 (Saturday session, holdout-based since markets were closed)
**Source:** `scripts/analyze_timeframe_heuristic.py`
**Dataset:** `historical_signals` × `signal_metrics` join, status='final', 91,831 rows
**Split:** 80/20 random with seed=42 → train=73,465 holdout=18,366

## Headline finding

| Heuristic | Clean-hit rate on holdout | Distribution |
|---|---|---|
| Placeholder (`assign_timeframe_for_backfill`) | **83.31%** | 89% 15m, 11% 30m |
| Naive empirical (mode of `best_tf` per bucket) | 70.71% | **100% 5m** |

**The placeholder beats the naive empirical heuristic by +12.6pp.**

## Why the empirical version under-performs

The `best_tf` column reports the **shortest** timeframe that classified `CLEAN_HIT`. Because `signal_metrics`'s threshold for CLEAN_HIT is 0.5% MFE and 94.8% of historical fires have *some* clean timeframe, the 5m bucket wins the "shortest clean" race almost every time.

But "shortest clean" ≠ "best to trade":

* A signal can be CLEAN_HIT at 5m, 15m, 30m, AND 60m simultaneously
* `best_tf` reports 5m as the winner
* Trading the 5m horizon means 5-minute scalps — far more noise than a 15m hold
* When we evaluate "did `cls_<predicted>` == CLEAN_HIT", the 5m prediction loses points to slippage/noise on bars where a 15m hold would have been cleaner

The placeholder's "high vol + strong → 15m, default → 30m" tier structure happens to align with "tradeable horizon AND clean" in a way the naive `mode-of-best_tf` does not.

## Top empirical buckets vs placeholder predictions

```
strategy        sig_str  atr      rsi     n        empirical   placeholder   agree
momentum        3        low      mid     27,155   5m          15m           no
momentum        3        avg      mid     25,604   5m          15m           no
momentum        3        high     mid     7,501    5m          30m           no
momentum        4        low      mid     3,433    5m          15m           no
momentum        4        avg      mid     3,198    5m          15m           no
momentum        3        low      high    1,020    5m          15m           no
momentum        4        high     mid     1,017    5m          15m           no
momentum        3        avg      high    970      5m          15m           no
momentum        3        low      low     682      5m          15m           no
momentum        3        unknown  mid     568      5m          15m           no
```

**Every bucket** predicts 5m empirically. Zero agreement with the placeholder. This is the smoking gun that the empirical methodology, not the placeholder, is the problem.

## Decision

* **Keep the placeholder** in production.
* **Do NOT integrate the naive empirical heuristic.**
* **Document this finding** so future Phase 1 refinement work uses a smarter target.

## Follow-up methodology to try

1. **Longest clean TF**: predict the longest TF where `cls_<tf> == CLEAN_HIT` instead of the shortest. Hypothesis: longer horizons are more stable and align better with "tradeable".
2. **TF-floor constraint**: predict the shortest clean TF among `{15m, 30m, 60m, 90m, 120m, 240m}` — exclude the 5m noise bucket.
3. **Multi-criteria target**: pick the TF that maximizes `mfe_60m_atrs / N` where N is the bar count to that TF (risk-adjusted return per minute held).
4. **Per-strategy targets**: maybe momentum and mean-reversion have fundamentally different optimal-tf distributions; train separate lookups.

Each of these is a fresh analysis, not a code change. The script (`scripts/analyze_timeframe_heuristic.py`) provides the scaffolding to swap targets and re-run.

## Methodology notes

* **Why 80/20 random not date-stratified**: signal-quality dynamics shouldn't time-leak — each row is independent enough. A more cautious version would split by date; the seed-deterministic random split is sufficient for this iteration.
* **Why "clean-hit at predicted TF" is the right metric**: the heuristic's purpose is to pick a TF the user will actually trade. Matching `best_tf` exactly is uninteresting — we care that whatever TF we pick resolves clean.
* **INSUFFICIENT_DATA exclusion**: holdout rows where `cls_<predicted_tf>` is INSUFFICIENT_DATA are dropped from the denominator — we couldn't evaluate them, so they're noise.

## Tests

22 hermetic tests in `tests/test_analyze_timeframe_heuristic.py` cover:
- Bucket boundary thresholds (ATR, RSI)
- Lookup-table mode logic + 'none' fallback
- Cold-start behavior
- Evaluator INSUFFICIENT_DATA handling
- Train/test split determinism
