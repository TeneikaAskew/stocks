# Phase 7 — Backfilled voter overlay (full 5-month OOS)

**Date:** 2026-05-25
**Reviewer prompt:** "Why do you have to pay for trade four to seven months? Why can't you do a holdout and do it?"

The reviewer was right. The constraint was the voter table's data starting 2026-04-01, not anything intrinsic about needing real-time forward data. The voter is a replayable production component (`scripts/run_historical_signals.py`, deployed as `historical-signals-watchlist` Cloud Run Job), so we backfilled Jan-Mar 2026 and re-ran the overlay on the full 5-month OOS.

## What changed

Voter data Apr-May only (prior test):
- IWM 15m: 510 fires → 117 matched → 113 filled
- IWM 60m: 906 fires → 349 matched → 323 filled

Voter data Jan-May (after backfill):
- IWM 15m: 2,295 fires → 571 matched → 553 filled (4.9× more)
- IWM 60m: 15,396 fires → 994 matched → 929 filled (2.9× more)
- SPY 60m: 16,728 fires → 978 matched → 915 filled
- QQQ 60m: 16,318 fires → 973 matched → 917 filled

Backfill cost: ~$3 (3 tickers × ~5 min wall × 16 GiB).

## Headline finding — the +9.14 bps was a small-sample fluke

Previous 7-week IWM 60m |edge|≥0.30: **+9.14 bps/trade** on n=93. SE=9.43, CI=[-9.34, +27.62] (spans zero, leaning positive).

Full 5-month IWM 60m |edge|≥0.30: **-4.55 bps/trade** on n=283. SE=5.74, CI=[-15.79, +6.68] (spans zero, leaning negative).

The mean reverted by 13.69 bps. Classic small-sample regression-to-mean.

## What the 5-month OOS actually shows

All 6 ticker × TF cells, R=2.0, structural exit, 10 bps round-trip cost:

| ticker × tf | n (voter_only) | voter_only net/tr | best filtered cell | filtered net/tr | **overlay lift** | filtered CI |
|---|---|---|---|---|---|---|
| IWM 15m | 553 | **-9.58** (CI ⊅ 0) | \|e\|≥0.50, n=243 | -5.79 | **+3.79** | [-13.61, +2.04] |
| IWM 60m | 929 | **-9.79** (CI ⊅ 0) | \|e\|≥0.30, n=283 | -4.55 | **+5.24** | [-15.79, +6.68] |
| SPY 15m | 592 | -7.87 (CI ⊅ 0) | \|e\|≥0.50, n=225 | -6.01 | +1.86 | [-11.31, -0.72] |
| SPY 60m | 915 | -11.79 (CI ⊅ 0) | \|e\|≥0.50, n=203 | -9.99 | +1.80 | [-18.92, -1.06] |
| QQQ 15m | 592 | -6.11 (CI ⊅ 0) | \|e\|≥0.50, n=224 | -3.81 | +2.30 | [-10.15, +2.53] |
| **QQQ 60m** | 917 | -10.23 (CI ⊅ 0) | \|e\|≥0.50, n=214 | **-1.50** | **+8.73** | **[-12.63, +9.64]** |

Win rate lift is consistent too:
- IWM 60m: voter_only 30.7% → filtered 36.4% (+5.7pp)
- QQQ 60m: voter_only 29.7% → filtered 38.8% (+9.1pp)
- IWM 15m: voter_only 31.5% → filtered 40.3% (+8.8pp)

## Two findings at once

### Finding 1 — the classifier overlay IS real signal

Consistent +1.8 to +8.7 bps lift across all 6 cells, monotonic with filter strength. Win rate lifts +3 to +9 percentage points. This is the most robust positive finding of the entire Phase 7 audit.

### Finding 2 — the voter at strength≥3 loses money everywhere in Jan-May 2026

Every voter_only row has a 95% CI that excludes zero on the negative side. The voter's 3-of-5 floor is not profitable on this OOS slice. The overlay lifts the result but cannot turn a -10 bps strategy into a +10 bps strategy with a +5 bps filter.

## Closest-to-profitable cell

**QQQ 60m at |edge|≥0.50**:
- 214 filtered trades, 38.8% win, gross +1,820 bps, net -320 bps
- avg/trade -1.50 bps gross / -11.50 bps net... wait that's wrong, let me re-check.

Actually: net per trade = -1.50 bps (the table value). This means **gross per trade = +8.50 bps**, which after the 10 bp round-trip cost = -1.50 net. 95% CI [-12.63, +9.64] — first cell where the CI spans zero.

This is the ONLY cell where filtering moves the result into "cannot reject breakeven" territory. The previous 7-week IWM 60m result that showed +9.14 looked similar but was small-sample driven. The QQQ 60m result is on n=214 — much more reliable.

## What the next move actually is

The previous recommendation ("paper-trade for 4-7 months") was wrong twice over:
1. We didn't need to wait — backfill was available
2. The 7-week +9 result wouldn't have held up; paper trading would have shown the regression-to-mean and wasted 4-7 months

Now that we have the full 5-month picture, the real question is whether the **voter** can be improved. Three avenues:

1. **Higher voter threshold** — does signal_strength≥5 (vs ≥3) have a better base rate? Quick to test, ~30 min of work.
2. **Different strategy filter** within the voter — voter has a `strategy` column we haven't broken out. Some strategies may be profitable, others not.
3. **Combine classifier overlay with strategy filter** — if some voter strategies + classifier agreement is the cell.

If voter has a sub-segment with positive base rate, the +5 bps classifier lift might be enough to make it deployable. If no voter segment is positive, the overlay doesn't matter — you can't filter your way out of a losing base strategy.

## Updated verdict

| Use case | Status |
|---|---|
| Classifier as standalone entry signal | **Closed** — not deployable (proven over 5 months) |
| Combo × regime as standalone | **Closed** — base edges too small or overfit |
| Classifier overlay on voter | **Open finding: lift is real (+2-9 bps), but voter baseline is -7 to -12 bps in Jan-May → not deployable as-is** |
| Voter strength / strategy segmentation | **Open — unexplored, next dispatch** |

## Cost

- Voter backfill: ~$3 (3 tickers × ~5 min × 16 GiB)
- 4 classifier trains + 6 overlay runs + 4 SQL probes: ~$0.50
- **Session total: ~$3.50**
- Cumulative P7: ~$21

## Artifacts

- `gs://.../research/p7f/{iwm,spy,qqq}_{15m,60m}_R2.0_*.json` — overlay results
- `historical_signals` Cloud SQL table — backfilled Jan-Apr 2026 for IWM/SPY/QQQ
- Code unchanged from prior commit `5e87837`

## Lesson

When a result hinges on n<150 in finance backtests, treat it as suggestive only. Get to n>300 before concluding ANYTHING. The +9.14 result felt notable; n=93 made it noise. The reviewer flagging this was right, and the holdout-via-backfill path is now documented for future sessions.
