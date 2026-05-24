# Phase 7 — Reverification of Prior-Audit Priority-1 Findings

Each row below was a P2/P3/P5 finding flagged as production-actionable in `docs/research/2026-05-23/P6_synthesis.md` §3. P7 reruns the same calculation against the new bar-level dataset to verify or refute.

| original finding | reverification cell | replicated? | notes |
|---|---|---|---|
| P3: 212_bear_continuation × HIGH-VIX, 5d, +5.15pp | 60m × fwd_5bars × VIX_HIGH | hit_pct = 51.8% on n=338 60m fwd-5bars events | |
| P3: clean_2d_bear × HIGH-VIX, 5d, +5.05pp | 60m × fwd_5bars × VIX_HIGH | hit_pct = 53.7% on n=341 | |
| P3: 322_bull_continuation, 5d, -2.79pp (anti) | 60m × fwd_5bars (all VIX) | hit_pct = 59.6% on n=1003 | |
| P5: flip_cross PUT × FTFC-DOWN at 15m, live=76.7% | needs gamma_events ⋈ strat_features_5m join | TODO | requires SQL via db-query.yml |
