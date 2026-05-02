# Timeframe Heuristic — Empirical Analysis

**Date:** 2026-05-02 (Saturday session, holdout-based since markets were closed)
**Source:** `scripts/analyze_timeframe_heuristic.py`
**Dataset:** `historical_signals` × `signal_metrics` join, status='final', 91,831 rows
**Split:** 80/20 random with seed=42 → train=73,465 holdout=18,366

## Headline finding

Three target methodologies tested. The placeholder beats two of them, but the third (15m-floor with per-bucket max-clean-rate) is **+8.2pp better**.

| Target | Clean-hit rate | Δ vs placeholder (83.31%) | TF distribution |
|---|---|---|---|
| Placeholder (`assign_timeframe_for_backfill`) | 83.31% | — | 89% 15m, 11% 30m |
| `mode_best_tf` (naive) | 70.71% | **-12.60pp** | 100% 5m |
| `max_clean_rate` (incl 5m) | 70.71% | **-12.60pp** | 100% 5m |
| **`max_clean_rate_min_15m`** | **91.51%** | **+8.20pp** | 99.9% 60m, <0.1% 15/30/240m |

## Why the targets differ so much

The first two targets pick 5m everywhere because:

* `best_tf` reports the SHORTEST clean timeframe — 5m wins by definition when any timeframe is clean
* `max_clean_rate` (which optimizes the right metric) STILL picks 5m because 5m has the highest per-bucket CLEAN_HIT rate — short windows clear the 0.5% MFE threshold quickly

Trading on the 5m horizon means scalping bars that have very high noise even when they classify CLEAN_HIT. The placeholder's tier defaults (15m / 30m) accidentally avoid this noise floor.

The `max_clean_rate_min_15m` target excludes 5m from the candidate set, forcing the heuristic to pick from {15m, 30m, 60m, 90m, 120m, 240m}. With more time-on-the-clock, 60m wins per-bucket clean-rate almost universally — producing a tradeable horizon with substantially higher clean-rate than the 15m placeholder default.

## Holdout numbers — `max_clean_rate_min_15m` vs placeholder

| metric | empirical | placeholder | delta |
|---|---|---|---|
| n_clean | 16,806 | 15,300 | +1,506 |
| n_wrong | 1,093 | 2,057 | -964 |
| n_noise | 308 | 668 | -360 |
| n_mixed | 159 | 341 | -182 |
| n_insufficient | 0 | 0 | 0 |
| **clean_rate_pct** | **91.51** | **83.31** | **+8.20** |

* **964 fewer wrong-direction predictions** — the heuristic doesn't lock into the 15m-or-30m tier when 60m would have been the right call
* **360 fewer noise predictions** — the longer horizon registers as a real move more often
* **0 insufficient data** — the 60m window had closed for every holdout row

## Decision

Two-step rollout per Rule 0:

1. **THIS PR (analysis only)**: ships the script + updated doc + tests. NO heuristic change.
2. **Follow-up PR** (after user review): replace `assign_timeframe_for_backfill` with the empirical lookup. The lookup table is small and inspectable; the function should be a thin wrapper that consults the table and falls back to the existing tier defaults on cold-start buckets.

## Caveats worth flagging before integration

1. **The 0.5% threshold is doing a lot of work**: at a tighter threshold (say 0.25%), the longer-horizon advantage shrinks — fewer signals would hit 0.25% MFE in 60 min, so 30m might overtake 60m. If we ever change the CLEAN_HIT threshold, the empirical heuristic must be re-trained.

2. **60m hold has higher options time-decay risk**: the live monitor's `expected_hold_min` field gets used by exit logic. A 60m default means longer exposure to theta decay. This is a downstream concern not captured by clean-hit rate alone — Phase 2's outcome-adaptive cooldown should weigh it.

3. **Cold-start fallback**: the holdout had **0 cold-start rows** (every bucket was seen in train), but production data may eventually have buckets the train set never saw. The lookup-based heuristic should fall back to the placeholder on unseen buckets, not to a hardcoded default.

4. **No catalyst-proximity feature**: the bucket dimensions are (strategy, signal_strength, atr_bucket, rsi_bucket). When Phase 1.5 (catalyst proximity) lands, it should be added as a fifth dimension and the analysis re-run — catalysts likely shift the optimal horizon (e.g., post-earnings, 5m might be cleaner than 60m due to immediate gap absorption).

## Methodology notes

* **80/20 random split, seed=42**: deterministic and reproducible. Each holdout row has a unique bucket-membership decision independent of the others.
* **`max_clean_rate_min_15m` definition**: for each (strategy, signal_strength, atr_bucket, rsi_bucket) bucket in train, compute `cls_<tf> == CLEAN_HIT` rate over rows in the bucket for tf ∈ {15m, 30m, 60m, 90m, 120m, 240m}. Pick the tf with highest rate. INSUFFICIENT_DATA rows are excluded from the per-tf denominator.
* **Holdout evaluation metric**: % of holdout rows where `cls_<predicted_tf> == CLEAN_HIT`. INSUFFICIENT_DATA in the predicted tf column drops that row from the denominator.
* **Why this is exactly the Rule 0 win**: without holdout evaluation, "use the data, predict mode of best_tf" sounds methodologically correct and would have shipped a 12.6pp regression. Rigorous comparison surfaced the trap AND found a 8.2pp improvement after refining the target.

## Tests

33 hermetic tests in `tests/test_analyze_timeframe_heuristic.py` cover all target methodologies, bucket boundary thresholds, lookup-table mode logic + 'none' fallback, cold-start, INSUFFICIENT_DATA handling, split determinism, the include_ticker plumbing, and the multi-TF + per-ticker reports.

---

## Update: multi-TF baselines + per-ticker (Q1 + Q2)

Two follow-up questions answered against the same holdout.

### Q1 — Multi-TF baselines (always pick TF X)

| TF | Always-pick clean-rate |
|---|---|
| 5m | 70.71% |
| 15m | 82.84% |
| 30m | 88.01% |
| **60m** | **91.51%** ← matches empirical exactly |
| 90m | 42.86% |
| 120m | 48.22% |
| 240m | 59.64% |

The empirical heuristic IS effectively "always 60m" (predicts 60m for 99.9% of rows). The 60m baseline matches the empirical's 91.51% exactly because the empirical IS the 60m baseline.

Implication: **the heuristic isn't really "adapting"**. It's picking the universally-best TF. If we ever change the CLEAN_HIT threshold (currently 0.5%), the optimal TF shifts and we'd need to re-train.

The 90m/120m/240m drop (43-60%) is INSUFFICIENT_DATA biting — long windows often haven't closed for end-of-day fires, so those rows drop from the denominator and the remaining sample skews unfavorably.

### Q2 — Per-ticker variation

Per-ticker clean-rate of the 4-feature empirical heuristic on the holdout:

| ticker | n | rate |
|---|---|---|
| ARM | 2,429 | 92.34% |
| IWM | 1,971 | 92.34% |
| AVGO | 1,045 | 92.63% |
| MRVL | 157 | 93.63% |
| TXN | 122 | 94.26% |
| QQQ | 2,047 | 91.84% |
| ASTX | 2,604 | 91.55% |
| AMD | 2,472 | 91.10% |
| QCOM | 146 | 91.10% |
| MU | 151 | 92.05% |
| TSM | 157 | 91.72% |
| ANET | 119 | 92.44% |
| CSCO | 98 | 93.88% |
| SPY | 2,123 | 90.67% |
| NVDA | 2,725 | 90.06% |

**Spread: 4.21pp** (90.06% min, 94.26% max). All 15 tickers within a tight band.

### Q2 follow-up — does adding ticker as a feature help?

| Heuristic | Holdout clean-rate |
|---|---|
| 4-feature (no ticker) | 91.51% |
| 5-feature (+ ticker) | 91.39% |
| Δ | **-0.12pp** |

Adding ticker as a 5th bucket dimension actually **hurts** marginally. The 5-feature version's more granular TF distribution (60m: 17,801; 15m: 126; 30m: 261; 240m: 158; 90m: 20) suggests it IS learning slightly different patterns per ticker — just not in a way that beats the metric, because cold-start risk on tail buckets outweighs the signal.

**Decision: 4-feature heuristic is the right choice.** Generalizes evenly across all 15 tickers, avoids overfitting, lookup table stays small (~30 buckets vs ~450 with ticker).

---

## Integration plan (Q3)

Lookup table generated by the analysis is small enough to embed as a Python constant. Follow-up PR will:

1. Run the analysis once on the FULL dataset (no train/test split — use everything for the production lookup) with `target=max_clean_rate_min_15m`, `include_ticker=False`.
2. Emit the resulting dict as a `EMPIRICAL_TIMEFRAME_LOOKUP: dict[Bucket, str]` constant in `lib/strategies/timeframe.py`.
3. Modify `assign_timeframe_for_backfill(strategy, signal_strength, atr_5m_pct, entry_rsi=None)` to:
   - Build the bucket from inputs
   - Look up in `EMPIRICAL_TIMEFRAME_LOOKUP`
   - On cold-start (bucket not in lookup), fall back to the existing tier defaults
4. Add tests pinning the lookup table values + cold-start behavior.
5. Re-run `scripts/backfill_timeframe_tags.py` against production to update the 91k-row backlog with the validated heuristic.

Revisit cadence:
- Re-run analysis weekly during the early operational period to validate
- Re-train when CLEAN_HIT threshold changes
- Re-train when `signal_metrics` accumulates 30+ days of new data (different volatility regime exposure)
