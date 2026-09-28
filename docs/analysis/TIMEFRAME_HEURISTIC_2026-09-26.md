# Timeframe Heuristic — Re-run After #1154

**Date:** 2026-09-26
**Supersedes:** [TIMEFRAME_HEURISTIC_2026-05-02.md](TIMEFRAME_HEURISTIC_2026-05-02.md)
**Issue:** #1167
**Source:** `scripts/analyze_timeframe_heuristic.py`, run on the production image through the `direction-probe` job with its args overridden (executions `direction-probe-nhtht` and `direction-probe-sv7vh`, read-only).
**Dataset:** `historical_signals` × `signal_metrics`, 244,326 joined rows; `best_tf` set on 155,134 (63.5%).
**Split:** 80/20 random with seed=42, as in May: train 195,461, holdout 48,865.

## Headline finding

With every timeframe classified on the same scale, the clean-hit rate rises steadily with the window, so "the timeframe with the highest clean rate" is always the longest one. The method behind `EMPIRICAL_LOOKUP` therefore cannot choose a holding timeframe: re-derived, it picks 240m for 50 of 52 buckets and for 48,823 of 48,865 holdout rows.

The May table's "60m everywhere" was the same artifact. #1154 found that 5m to 60m were classified with a cut-point 100 times too lenient, while 90m onward used the correct one. That made 60m the longest window on the lenient scale, so it won.

## Always-pick clean rate on the holdout

| TF | 2026-05-02 (5–60m lenient) | 2026-09-26 (all on 0.5%) |
|---|---:|---:|
| 5m | 70.71% | 6.98% |
| 15m | 82.84% | 14.98% |
| 30m | 88.01% | 22.79% |
| 60m | 91.51% | 32.10% |
| 90m | 42.86% | 43.73% |
| 120m | 48.22% | 48.26% |
| 240m | 59.64% | 60.31% |

90m onward barely moved: they were already on the correct scale. 5m to 60m fell by 60 to 64 points. The May document explained the drop after 60m as INSUFFICIENT_DATA; it was the unit change.

## The re-derived lookup

`--target=max_clean_rate_min_15m` (the May methodology): 52 buckets, all `momentum`.
- 50 buckets pick 240m.
- `(momentum, 4, avg, high)` picks 60m (120 training rows).
- `(momentum, 4, high, high)` picks 120m (49 training rows).

Holdout: 240m 48,823, 60m 28, 120m 13, 30m 1. Clean rate 60.30%, the always-240m rate. `--target=max_clean_rate` (5m included) gives the identical evaluation. The placeholder picks 15m for 46,480 rows and 30m for 2,385, with a clean rate of 15.45%.

## Why the metric cannot choose

CLEAN_HIT means the favorable excursion reached +0.5% (`classify`, `scripts/signal_quality_report.py:92-114`). Every window measures that excursion from the entry:
- 5m to 60m take the best one-minute close in the window (`lib/trading_analysis.py:925-936`).
- 90m to 240m take the best bar high or low (`extend_returns_from_intraday`, `scripts/signal_quality_report.py:152-192`).

Nested windows can only grow, so the rate rises with the window by construction, whatever the signal. The switch from closes to highs and lows at 90m adds to the step there. Maximising the rate selects the longest candidate, which says nothing about how long a trade from that signal should be held. May's "+8.2pp over the placeholder" compared a 60m window with a mostly-15m one, on the lenient scale.

## Decision

**Retire the lookup and re-tag history** (#1167, decided 2026-09-27).

- `EMPIRICAL_LOOKUP` and its bucket helpers are removed. `assign_timeframe_for_backfill` returns the placeholder tiers (`_placeholder_assign`): `assign_timeframe`'s tiers without RVOL, the same family the live monitor tags `signal_alerts` with.
- `scripts/backfill_timeframe_tags.py --retag` rewrites the existing `historical_signals.timeframe_tag` values. It writes only the rows whose tag or hold changes, so historical tags follow the rule that is actually in force.
- `historical_signals.timeframe_tag` has no live reader today; the ones found are under `gcp/research/_archive/`. The tag records the expected holding horizon and is not a trade instruction.

**What a real choice of timeframe would need.** A criterion that does not grow with the window by construction. Examples: the shortest window whose clean rate reaches a target, or the excursion per minute held, net of the adverse move over the same window. None has been evaluated. Until one is, the placeholder is the documented default, not an empirical result.

## Reproduce

```
gcloud run jobs execute direction-probe --region=us-east1 --async \
  --args="-m,scripts.analyze_timeframe_heuristic,--target=max_clean_rate_min_15m,--multi-tf-baselines,--top-buckets=1000"
```

Any bare-`python` job on an image that carries the script works; its output is in Cloud Logging under the execution name.
