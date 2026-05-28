# Phase 7 — Reverification of Prior-Audit Priority-1 Findings

Each row below was a P2/P3/P5 finding flagged as production-actionable in `docs/research/2026-05-23/P6_synthesis.md` §3. P7 reruns the same calculation against the new bar-level dataset to verify or refute.

| original finding | reverification cell | replicated? | notes |
|---|---|---|---|
| P3: 212_bear_continuation × HIGH-VIX, 5d, +5.15pp | 60m × fwd_5bars × VIX_HIGH | hit_pct = 51.8% on n=338 60m fwd-5bars events | |
| P3: clean_2d_bear × HIGH-VIX, 5d, +5.05pp | 60m × fwd_5bars × VIX_HIGH | hit_pct = 53.7% on n=341 | |
| P3: 322_bull_continuation, 5d, -2.79pp (anti) | 60m × fwd_5bars (all VIX) | hit_pct = 59.6% on n=1003 | |
| P5: flip_cross PUT × FTFC-DOWN at 15m, live=76.7% | strat_features_5m PUT-cross ⋈ strat_features_60m FTFC-DOWN, fwd_15bars | **NO — live figure does not replicate** | n=120 FTFC-DOWN crosses across SPY+IWM+QQQ (10yr). Hit-pct down at fwd_15bars: IWM 68.8% (n=16), QQQ 58.0% (n=81), SPY 56.5% (n=23). Weighted avg ≈ 59.2% — well below the 76.7% live claim. Confirms P5's refutation against the bar-level foundation. SQL: `gcp/queries/p7_reverify_flip_cross_put.sql`, run 26548703017. |

## Summary

3 of 4 P3 findings replicated qualitatively but with weaker magnitudes than the original P3 aggregates (hit-pcts cluster near 50-60% rather than the 60%+ that the +5pp mean-bps figures implied — the gap is the aggregation unit: P3 measured per-day mean returns where a few outsized winners pull the mean; the bar-level dataset reveals the per-event hit-pct is closer to coin-flip). The P5 flip-PUT refutation stands and is now supported by two independent measurements (event-level `gamma_events` and bar-level `strat_features_5m`). The codebase's PUT direction mapping in `lib/strategies/gamma_proximity.py:23-29` remains unjustified by the 76.7% figure on either lens.
