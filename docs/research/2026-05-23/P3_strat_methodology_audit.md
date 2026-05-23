# Phase 3 — Strat Methodology Edge Audit

**Date:** 2026-05-23
**Universe:** Top-100 by 60-day ADV (99 after excluding NBIS — see §4.1)
**Window:** 2016-01-01 → 2026-05-21 (~10 years of daily bars)
**Total events:** 204,275 (combo classifications × tickers × dates)
**Status:** Complete

## TL;DR

1. **Most strat combos have NO edge over baseline at the daily horizon.** The two most-common combos (`22_bull_continuation` and `22_bear_continuation`, together 35% of all events) have lifts within ±1pp.
2. **One combo is statistically significantly ANTI-PREDICTIVE**: `322_bull_continuation` has **−2.79pp 5d lift (p=0.002, N=2,961)**. Acting on this signal loses money more reliably than chance.
3. **The signal-positive combos are bear-side**: `212_bear_continuation` (+2.59pp, p=0.003) and `clean_2d_bear` (+1.86pp, p=0.044). HIGH-VIX regime amplifies both to +5pp lift.
4. **`f2d_bull_reversal` is the highest 1-day lift** (+5.73pp, p=0.006) but small N=577. Worth tracking but not yet conclusive.
5. **The `ftfc_direction` column is essentially empty for the broader universe** (only 11 of 206,463 rows have a value). Phase 3 could not stratify by FTFC at the per-ticker level. This is a Phase 1 finding the audit revealed only when actually using it.
6. **NBIS has a data-quality bug**: 552 events of `111_inside_compression` with hit_1d=0% — statistically impossible without a split/adjustment issue. Quarantined from the analysis.

## 1. Data envelope

| input | source | rows |
|---|---|---|
| Daily bars + pre-computed strat columns | `market_data_daily` for 100-ticker universe, date ≥ 2016-01-01 | ~253,000 raw |
| Strat classifier output | `strat_combo`, `strat_candle`, `strat_setup`, `ftfc_score`, `ftfc_direction` columns | populated by the existing daily fetcher |
| VIX | `^VIX.close` from Phase 1 backfill, joined on `date` | 2,864 days |
| Forward closes | `LEAD(close, 1/5/20)` over `(ticker ORDER BY date)` for 1d/5d/20d horizons | computed in single SQL |

Server-side aggregation by `(ticker, strat_combo, ftfc_direction, vix_tercile)` returned 3,550 cells (well under db-query.yml's 50k row cap, which the initial raw-row pull would have hit at ~5x over).

## 2. The combo-level headline (ex-NBIS, 99 tickers)

Universe-wide unconditional baselines:
- pct_up at 1d: **52.16%**
- pct_up at 5d: **54.87%**
- pct_up at 20d: **57.69%**

Per-combo pooled (sorted by 5d lift):

| combo | n | hit_1d | hit_5d | hit_20d | lift_1d | lift_5d | lift_20d |
|---|---|---|---|---|---|---|---|
| `312_bear_reversal` | 55 | 50.91 | **63.64** | 60.00 | -1.25 | +8.77 | +2.31 |
| `32_bear_reversal` | 62 | 53.23 | **62.90** | 69.36 | +1.07 | +8.04 | +11.67 |
| `11_inside_compression` | 318 | 52.52 | **60.38** | 63.44 | +0.36 | +5.51 | +5.75 |
| `f2d_bull_reversal` | 577 | **57.89** | 58.12 | 56.68 | +5.73 | +3.25 | -1.01 |
| `132_bear_continuation` | 221 | 52.04 | 57.92 | 59.24 | -0.12 | +3.05 | +1.55 |
| `212_bear_continuation` | 3,199 | 53.36 | **57.46** | 58.69 | +1.20 | **+2.59** | +1.00 |
| `322_bear_continuation` | 2,349 | 55.00 | 56.73 | 59.78 | +2.84 | +1.86 | +2.09 |
| `clean_2d_bear` | 2,925 | 54.09 | 56.72 | 58.04 | +1.93 | +1.86 | +0.35 |
| `32_bull_reversal` | 110 | 49.09 | 55.46 | 60.40 | -3.07 | +0.59 | +2.71 |
| `132_bull_continuation` | 314 | 52.23 | 55.41 | 57.08 | +0.07 | +0.55 | -0.61 |
| `212_bull_reversal` | 6,094 | 52.46 | 55.32 | 57.55 | +0.30 | +0.46 | -0.14 |
| `22_bear_reversal` | 28,555 | 52.50 | 55.11 | 57.51 | +0.34 | +0.24 | -0.18 |
| `212_bear_reversal` | 5,522 | 52.21 | 55.02 | 58.96 | +0.05 | +0.15 | +1.27 |
| `22_bull_reversal` | 29,062 | 51.59 | 54.97 | 57.31 | -0.56 | +0.10 | -0.38 |
| `22_bull_continuation` | 41,304 | 51.80 | 54.63 | 57.47 | -0.36 | -0.24 | -0.22 |
| `212_bull_continuation` | 4,310 | 50.95 | 54.50 | 57.12 | -1.21 | -0.37 | -0.57 |
| `312_bull_reversal` | 1,126 | 53.82 | 54.16 | 59.54 | +1.66 | -0.71 | +1.85 |
| `22_bear_continuation` | 30,741 | 52.86 | 54.11 | 57.10 | +0.71 | -0.76 | -0.59 |
| `f2u_bear_reversal` | 328 | 51.53 | 53.96 | 56.13 | -0.63 | -0.90 | -1.56 |
| `clean_2u_bull` | 2,870 | 50.94 | 53.42 | 58.39 | -1.22 | -1.45 | +0.70 |
| `322_bull_continuation` | 2,961 | 51.44 | **52.07** | 59.25 | -0.72 | **-2.79** | +1.56 |
| `111_inside_compression` (residual after NBIS) | 29 | 24.14 | 44.82 | 86.21 | -28.02 | -10.04 | +28.52 |

Z-test significance (cells with N≥30, against universe baseline):

| combo | n | lift_5d | p_5d | verdict |
|---|---|---|---|---|
| `322_bull_continuation` | 2,961 | **-2.79** | **0.002** | **ANTI-PREDICTIVE** — significant after FDR |
| `212_bear_continuation` | 3,199 | **+2.59** | **0.003** | **POSITIVE EDGE** — significant |
| `22_bear_continuation` | 30,741 | -0.76 | 0.008 | mild negative — very large N, real effect but tiny |
| `clean_2d_bear` | 2,925 | +1.86 | 0.044 | small positive edge |
| `11_inside_compression` | 318 | +5.51 | 0.048 | medium edge, thin N |
| `322_bear_continuation` | 2,349 | +1.86 | 0.070 | small positive, borderline |
| `f2d_bull_reversal` | 577 | +3.25 | 0.116 | positive but n.s. at 5d (significant at 1d, +5.73, p=0.006) |

Reading: **the only combos with both (statistical significance) AND (meaningful lift > 2pp) are `322_bull_continuation` (negative edge), `212_bear_continuation` (positive edge), and `f2d_bull_reversal` (1d-only, small N)**. Everything else is at-baseline or borderline.

## 3. VIX-regime amplification

At HIGH VIX (≥19.40), bear continuation combos pick up substantial edge:

| combo | VIX | n | hit_5d | lift_5d |
|---|---|---|---|---|
| `212_bear_continuation` | HIGH | 1,373 | 60.01 | **+5.15** |
| `clean_2d_bear` | HIGH | 1,235 | 59.92 | **+5.05** |
| `212_bull_reversal` | HIGH | 1,983 | 58.19 | +3.33 |
| `212_bear_continuation` | LOW | 734 | 58.17 | +3.31 |
| `322_bear_continuation` | HIGH | 1,377 | 57.73 | +2.87 |
| `22_bear_reversal` | HIGH | 10,440 | 57.40 | +2.54 |
| `clean_2d_bear` | LOW | 654 | 57.19 | +2.32 |

**Pattern**: HIGH VIX × bear-side combos = best edge. This is the volatility-expansion regime where direction follows-through. LOW and MID VIX bear cells also work but less.

The largest-N bull-side combo is `22_bull_continuation` (LOW VIX, N=14,446), which barely beats baseline (+0.56pp). The bull side is essentially eaten by the secular bull-drift baseline.

## 4. Data quality findings (must be addressed before production use)

### 4.1 NBIS — `111_inside_compression` bug

NBIS has **552 events of `111_inside_compression` with hit_1d=0%** across LOW/MID/HIGH VIX cells. This is statistically impossible for a liquid stock under normal conditions; it implies either:

- A split / dividend / adjustment NOT reflected in the `c1d` close
- The `111_inside_compression` classifier mis-firing on bars whose close was already at the day's low
- NBIS data ingestion has a systematic issue (the ticker started 2024-10-21 in our intraday data, so it's a newer addition — fetcher may need a per-ticker adjustment pass)

NBIS-only baseline = 38.83% vs universe 52.16% — confirms a data-quality skew, not a real "bear regime" finding.

**Action**: dispatch a follow-up SQL query to inspect NBIS daily bars for adjustment discontinuities, and either (a) reapply split-adjusted closes or (b) exclude NBIS from the universe until fixed.

### 4.2 `ftfc_direction` column is unpopulated

Only 11 of 206,463 rows have `ftfc_direction` set. The fetcher that populates this column (likely `gcp/fetchers/fetch_market_data.py` or a follow-up processor) is either not running for the broader universe, or only computes it for the 3 ETFs.

This blocks the originally-planned `combo × ftfc × vix` stratification. **Action**: add a backfill task for `ftfc_direction` across all 100-ticker × 10yr daily bars, then re-run this audit. If `ftfc_direction` adds another 5-10pp on top of `212_bear_continuation`'s +5pp HIGH-VIX edge, that's an actionable trading signal.

## 5. Verdict on pre-registered hypotheses

| H | hypothesis | verdict |
|---|---|---|
| H1 (revisited from P2) | Strat combos beat baseline at daily horizon | **PARTIAL** — only 2 of 22 combos are FDR-significant at 5d, but lifts are small (+2-5pp not the +30pp we'd want) |
| H6 | FTFC alignment boosts edge | **UNTESTABLE** — column unpopulated |
| H8 | Negative gamma regime amplifies signals | **NOT TESTED** in P3 (P3 doesn't have intraday gamma context); HIGH-VIX is a partial proxy and DOES amplify bear-side combos |

## 6. Implications for production

1. **DEPRIORITIZE `322_bull_continuation` as a trade signal.** It's significantly anti-predictive at 5d horizon (p=0.002). Either don't act on it, or take the opposite side.
2. **The most actionable combo is `212_bear_continuation` in HIGH-VIX regime** — +5.15pp lift at 5d horizon, N=1,373, statistically robust.
3. **`clean_2d_bear` in HIGH-VIX** is a strong second (+5.05pp, N=1,235).
4. **Don't size up on `22_bull_continuation` or `22_bear_reversal`** — they're the most common combos (35% of events) but have ≤±1pp edge.
5. **Fix the NBIS data first**, then the `ftfc_direction` backfill. Both block deeper Phase 3 analysis.

## 7. Open follow-ups

- Same audit with `ftfc_direction` properly populated (would resolve H6 and unlock H8-style analysis for the broader universe).
- NBIS data quality investigation + remediation.
- Per-ticker exploration of which combos best fit each name — possible that mega-caps like AAPL/MSFT have different combo-edges than small-caps like RKLB/IONQ.
- Combo-pair sequencing: does (yesterday `clean_2d_bear` HIGH-VIX) → (today entry) have stronger edge than the unconditional combo?

## 8. Artifacts

| artifact | path |
|---|---|
| Raw cell aggregates | [`data/p3_strat_cells.csv`](data/p3_strat_cells.csv) — 3,550 cells |
| Outcomes grid (ex-NBIS) | [`data/p3_outcomes_grid_ex_nbis.csv`](data/p3_outcomes_grid_ex_nbis.csv) |
| Combo-pooled | [`data/p3_combo_pooled.csv`](data/p3_combo_pooled.csv) |
| Per-ticker baselines | [`data/p3_ticker_baselines.csv`](data/p3_ticker_baselines.csv) |
