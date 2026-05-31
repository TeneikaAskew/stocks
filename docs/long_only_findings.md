# Long-Only Earnings Strategy — Findings (2026-05-22)

Detail report from `scripts/calibrate_earnings.py --long-only-detail` run
against the 2,533 historical Q5 (top-conviction) earnings events with
options snapshots backfilled 2026-05-21 → 2026-05-22.

The PR-B headline (`realized_vs_implied_ratio=0.636` across all Q5,
short-strangle +20%) is the MEAN. This report unpacks the distribution
for traders who only **BUY** premium (long straddles, long strangles,
long calls, long puts) and never sell.

## Q5 splits into three wildly different buckets

| Bucket | n | Long Straddle hit / mean | Long Call hit / mean | Long Put hit / mean |
|---|---|---|---|---|
| **Ratio > 1.5** (realized way bigger than implied) | 205 (8%) | **91% / +117%** | 51% / +142% | 47% / +91% |
| Ratio 0.85–1.5 (fairly priced) | 540 (21%) | 56% / +18% | 44% / +32% | 39% / +5% |
| Ratio < 0.85 (over-priced — the IC subset) | 1,788 (71%) | 22% / **−32%** | 23% / **−39%** | 30% / **−32%** |

p90 / p10 columns in the raw report show the tails — best wins on long
straddle in the >1.5 bucket reach +220% return on premium paid; worst
losses in the <0.85 bucket bottom out around the full premium.

## The selection rule — implied move size matters

Long-win events (ratio > 1.5) average **implied = 12.1%, realized = 23.9%**.
Long-skip events (ratio < 0.85) average **implied = 18.0%, realized = 4.7%**.

**Smaller implied moves are easier to beat.** When the options market
prices an ordinary 10-15% earnings move but the stock actually moves
25%+, long premium pays multiples. When the market prices a "huge"
20%+ move and the stock disappoints, long premium gets crushed.

| Implied move size | Long-side recommendation |
|---|---|
| **< 10%** | Long premium has real edge if conviction is high. Long straddle is the safe play; long call/put if the archetype is directional. |
| 10–15% | Coin flip. Skip unless you have a strong directional view. |
| 15–20% | Mostly over-priced. Long premium loses on average. |
| **> 20%** | Almost always over-priced. Skip — these are the IC-eligible events. |

## Named winners (worked-dollar examples)

### Long Straddle — top 10 historical winners
| Ticker | Date | Move | Implied → Realized | PnL % | $ paid → $ exit per contract |
|---|---|---|---|---|---|
| NVAX | 2024-05-10 | 124.2% | 10.2% → 124.2% (ratio 12.20) | +1,792% | $46 → $861 |
| LUMN | 2024-08-06 | 44.4% | 27.4% → 44.4% (ratio 1.62) | +482% | $71 → $413 |
| RKLB | 2026-05-08 | 9.5% | 8.8% → 9.5% (ratio 1.08) | +456% | $690 → $3,835 |
| TWLO | 2020-05-06 | 24.5% | 9.4% → 24.5% (ratio 2.60) | +391% | $1,098 → $5,389 |
| INOD | 2026-05-07 | 59.8% | 17.1% → 59.8% (ratio 3.50) | +377% | $795 → $3,789 |
| ISSC | 2025-12-18 | 25.3% | 13.2% → 25.3% (ratio 1.92) | +356% | $145 → $661 |
| AAP | 2025-05-22 | 37.6% | 12.4% → 37.6% (ratio 3.02) | +341% | $390 → $1,717 |
| APEI | 2023-03-14 | 23.9% | 13.6% → 23.9% (ratio 1.76) | +335% | $125 → $544 |
| FSLY | 2026-02-11 | 44.9% | 18.2% → 44.9% (ratio 2.47) | +327% | $165 → $704 |
| INOD | 2024-11-07 | 24.6% | 18.7% → 24.6% (ratio 1.32) | +317% | $450 → $1,878 |

### Long Call — top 10 (direction-correct upside)
| Ticker | Date | Move | PnL % | $ paid → $ exit per contract |
|---|---|---|---|---|
| NVAX | 2024-05-10 | ↑124% | **+3,905%** | $22 → $861 |
| TSAT | 2025-06-18 | ↑0.5% | +2,800% | $10 → $290 |
| RKLB | 2026-05-08 | ↑9.5% | +1,071% | $328 → $3,835 |
| ARLO | 2023-03-07 | ↑16.2% | +988% | $12 → $136 |
| TWLO | 2020-05-06 | ↑24.5% | +931% | $522 → $5,389 |
| INOD | 2026-05-07 | ↑59.8% | +924% | $370 → $3,789 |
| LUMN | 2024-08-06 | ↑44.4% | +920% | $40 → $413 |
| AAP | 2025-05-22 | ↑37.6% | +851% | $181 → $1,717 |
| STNE | 2023-11-10 | ↑4.0% | +814% | $18 → $160 |
| MGNI | 2023-05-10 | ↑12.7% | +736% | $22 → $188 |

### Long Put — top 10 (direction-correct downside)
| Ticker | Date | Move | PnL % | $ paid → $ exit per contract |
|---|---|---|---|---|
| ASYS | 2023-12-14 | ↓2.2% | +970% | $10 → $107 |
| SLQT | 2024-09-13 | ↓29.2% | +793% | $8 → $67 |
| STIM | 2023-03-07 | ↓8.6% | +733% | $15 → $125 |
| ALGN | 2025-07-30 | ↓30.0% | +664% | **$995 → $7,599** |
| STNE | 2021-11-16 | ↓17.3% | +598% | $148 → $1,030 |
| SKYT | 2024-05-08 | ↓12.9% | +570% | $50 → $335 |
| LFMD | 2025-08-05 | ↓36.7% | +563% | $82 → $547 |
| Z | 2021-11-02 | ↓15.4% | +557% | $480 → $3,153 |
| RCEL | 2023-05-11 | ↓1.2% | +542% | $45 → $289 |
| ASRT | 2023-11-08 | ↓45.5% | +532% | $12 → $79 |

## Archetype distribution (mostly the same across winners and losers)

| Archetype | In long-wins (n=205) | In long-skips (n=1,788) |
|---|---|---|
| mixed | 69% | 59% |
| reversal_play | 17% | 27% |
| bullish_trend | 9% | 8% |
| bearish_trend | 5% | 6% |

Archetype alone is NOT a strong filter for long-only selection — the
implied-move-size filter dominates. The IC mode wired into the brief
(PR-B `recommended_structure()`) ignores archetype too once the
calibration confirms over-pricing.

## What's not yet wired up

1. **Long-only brief mode.** `lib/earnings_reactions.recommended_structure()`
   currently returns 'IC' for Q5 + over-priced. A future flag like
   `RECOMMEND_LONG_ONLY=true` would return one of LONG STRADDLE / LONG CALL /
   LONG PUT / SKIP based on implied-move size + archetype. Trivial to add.

2. **A weekly "long-candidate watchlist".** Cloud Run job that scans
   next week's earnings calendar, filters to (implied_move < 15%) AND
   (playability_score in Q4/Q5) AND (history shows the ticker has at
   least one prior ratio>1.5 event), and posts the list to Discord
   Sunday night. Identifies the "next NVAX" candidates before the event.

## Reproducing this report

```bash
gcloud run jobs execute earnings-sweep --region=us-east1 \
  --args="--no-apply,--long-only-detail" --wait

# Then scrape the BEGIN/END markers from the execution logs:
gcloud beta run jobs executions logs read <exec-id> --region=us-east1 \
  | awk '/BEGIN LONG-ONLY REPORT/,/END LONG-ONLY REPORT/'
```

Auto-refreshes whenever the underlying earnings_options_snapshots
backfill grows or the calibration row updates. No DB writes — output
goes only to stdout / Cloud Run logs.
