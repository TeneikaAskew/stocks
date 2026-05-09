# Momentum Strategy — Fire-Eligibility Analysis

**Date generated**: 2026-05-09  
**Lookback**: 50 calendar days (≈ 35 trading days)  
**Strategy**: `lib/strategies/momentum.py` (7 conditions per direction)  
**Live MIN_CONDITIONS**: 5 (current production gate)  
**Live MIN_CORE_CONDITIONS gate**: 2 (would-fire counts apply this)  

## Background

Audit 2026-05-08 found 0 momentum fires across SPY/IWM/QQQ in 50 days. This report tests hypothesis (a) — the strategy reached `evaluate()` but never crossed MIN_CONDITIONS — by replaying both condition checks against historical 1-min bars. Hypothesis (b) (orchestration excludes the strategy) is answered by Track D's instrumentation half (issue #312).

## IWM

**Bars evaluated**: 33,543

### CALL

**Per-condition fire rate** (% of bars where condition scored):

| Condition | Fires | % of bars |
|---|---:|---:|
| `above_vwap` | 18,583 | 55.4% |
| `above_ema9` | 17,328 | 51.7% |
| `rsi_bullish_recovery` | 15,425 | 46.0% |
| `rvol_above_recent` | 13,381 | 39.9% |
| `rsi_thrust` | 7,332 | 21.9% |
| `atr_expansion` | 5,658 | 16.9% |
| `consecutive_up` | 3,359 | 10.0% |

**Score distribution**:

| Score | Bars | % |
|---:|---:|---:|
| 0 | 599 | 1.8% |
| 1 | 6,834 | 20.4% |
| 2 | 12,005 | 35.8% |
| 3 | 8,310 | 24.8% |
| 4 | 3,995 | 11.9% |
| 5 | 1,496 | 4.5% |
| 6 | 296 | 0.9% |
| 7 | 8 | 0.0% |

**Would-fire count at each MIN_CONDITIONS threshold** (after MIN_CORE_CONDITIONS=2 gate, which mirrors the live `MomentumStrategy.evaluate()`):

| Threshold | With core gate | % | Without core gate (diagnostic) | Δ confirmer-only |
|---:|---:|---:|---:|---:|
| ≥ 3 | 12,249 | 36.5% | 14,105 | 1,856 |
| ≥ 4 | 5,558 | 16.6% | 5,795 | 237 |
| ≥ 5 | 1,800 | 5.4% | 1,800 | 0 |  ← live
| ≥ 6 | 304 | 0.9% | 304 | 0 |

### PUT

**Per-condition fire rate** (% of bars where condition scored):

| Condition | Fires | % of bars |
|---|---:|---:|
| `rsi_bearish_recovery` | 17,146 | 51.1% |
| `below_ema9` | 16,207 | 48.3% |
| `below_vwap` | 14,931 | 44.5% |
| `rvol_above_recent` | 13,381 | 39.9% |
| `rsi_thrust` | 7,226 | 21.5% |
| `atr_expansion` | 5,658 | 16.9% |
| `consecutive_down` | 3,119 | 9.3% |

**Score distribution**:

| Score | Bars | % |
|---:|---:|---:|
| 0 | 697 | 2.1% |
| 1 | 8,050 | 24.0% |
| 2 | 11,967 | 35.7% |
| 3 | 7,541 | 22.5% |
| 4 | 3,681 | 11.0% |
| 5 | 1,310 | 3.9% |
| 6 | 292 | 0.9% |
| 7 | 5 | 0.0% |

**Would-fire count at each MIN_CONDITIONS threshold** (after MIN_CORE_CONDITIONS=2 gate, which mirrors the live `MomentumStrategy.evaluate()`):

| Threshold | With core gate | % | Without core gate (diagnostic) | Δ confirmer-only |
|---:|---:|---:|---:|---:|
| ≥ 3 | 10,689 | 31.9% | 12,829 | 2,140 |
| ≥ 4 | 4,992 | 14.9% | 5,288 | 296 |
| ≥ 5 | 1,607 | 4.8% | 1,607 | 0 |  ← live
| ≥ 6 | 297 | 0.9% | 297 | 0 |

## QQQ

**Bars evaluated**: 35,519

### CALL

**Per-condition fire rate** (% of bars where condition scored):

| Condition | Fires | % of bars |
|---|---:|---:|
| `above_vwap` | 21,829 | 61.5% |
| `above_ema9` | 18,766 | 52.8% |
| `rsi_bullish_recovery` | 15,212 | 42.8% |
| `rvol_above_recent` | 13,417 | 37.8% |
| `rsi_thrust` | 8,124 | 22.9% |
| `atr_expansion` | 5,618 | 15.8% |
| `consecutive_up` | 4,104 | 11.6% |

**Score distribution**:

| Score | Bars | % |
|---:|---:|---:|
| 0 | 600 | 1.7% |
| 1 | 7,017 | 19.8% |
| 2 | 12,811 | 36.1% |
| 3 | 8,604 | 24.2% |
| 4 | 4,229 | 11.9% |
| 5 | 1,859 | 5.2% |
| 6 | 385 | 1.1% |
| 7 | 14 | 0.0% |

**Would-fire count at each MIN_CONDITIONS threshold** (after MIN_CORE_CONDITIONS=2 gate, which mirrors the live `MomentumStrategy.evaluate()`):

| Threshold | With core gate | % | Without core gate (diagnostic) | Δ confirmer-only |
|---:|---:|---:|---:|---:|
| ≥ 3 | 13,329 | 37.5% | 15,091 | 1,762 |
| ≥ 4 | 6,289 | 17.7% | 6,487 | 198 |
| ≥ 5 | 2,258 | 6.4% | 2,258 | 0 |  ← live
| ≥ 6 | 399 | 1.1% | 399 | 0 |

### PUT

**Per-condition fire rate** (% of bars where condition scored):

| Condition | Fires | % of bars |
|---|---:|---:|
| `rsi_bearish_recovery` | 18,848 | 53.1% |
| `below_ema9` | 16,745 | 47.1% |
| `below_vwap` | 13,690 | 38.5% |
| `rvol_above_recent` | 13,417 | 37.8% |
| `rsi_thrust` | 8,081 | 22.8% |
| `atr_expansion` | 5,618 | 15.8% |
| `consecutive_down` | 3,670 | 10.3% |

**Score distribution**:

| Score | Bars | % |
|---:|---:|---:|
| 0 | 800 | 2.3% |
| 1 | 9,436 | 26.6% |
| 2 | 12,527 | 35.3% |
| 3 | 7,420 | 20.9% |
| 4 | 3,681 | 10.4% |
| 5 | 1,341 | 3.8% |
| 6 | 308 | 0.9% |
| 7 | 6 | 0.0% |

**Would-fire count at each MIN_CONDITIONS threshold** (after MIN_CORE_CONDITIONS=2 gate, which mirrors the live `MomentumStrategy.evaluate()`):

| Threshold | With core gate | % | Without core gate (diagnostic) | Δ confirmer-only |
|---:|---:|---:|---:|---:|
| ≥ 3 | 10,536 | 29.7% | 12,756 | 2,220 |
| ≥ 4 | 5,056 | 14.2% | 5,336 | 280 |
| ≥ 5 | 1,655 | 4.7% | 1,655 | 0 |  ← live
| ≥ 6 | 314 | 0.9% | 314 | 0 |

## SPY

**Bars evaluated**: 35,548

### CALL

**Per-condition fire rate** (% of bars where condition scored):

| Condition | Fires | % of bars |
|---|---:|---:|
| `above_vwap` | 22,615 | 63.6% |
| `above_ema9` | 18,605 | 52.3% |
| `rsi_bullish_recovery` | 15,589 | 43.9% |
| `rvol_above_recent` | 13,718 | 38.6% |
| `rsi_thrust` | 8,077 | 22.7% |
| `atr_expansion` | 5,883 | 16.5% |
| `consecutive_up` | 4,050 | 11.4% |

**Score distribution**:

| Score | Bars | % |
|---:|---:|---:|
| 0 | 526 | 1.5% |
| 1 | 6,564 | 18.5% |
| 2 | 12,781 | 36.0% |
| 3 | 8,937 | 25.1% |
| 4 | 4,503 | 12.7% |
| 5 | 1,853 | 5.2% |
| 6 | 365 | 1.0% |
| 7 | 19 | 0.1% |

**Would-fire count at each MIN_CONDITIONS threshold** (after MIN_CORE_CONDITIONS=2 gate, which mirrors the live `MomentumStrategy.evaluate()`):

| Threshold | With core gate | % | Without core gate (diagnostic) | Δ confirmer-only |
|---:|---:|---:|---:|---:|
| ≥ 3 | 14,030 | 39.5% | 15,677 | 1,647 |
| ≥ 4 | 6,533 | 18.4% | 6,740 | 207 |
| ≥ 5 | 2,237 | 6.3% | 2,237 | 0 |  ← live
| ≥ 6 | 384 | 1.1% | 384 | 0 |

### PUT

**Per-condition fire rate** (% of bars where condition scored):

| Condition | Fires | % of bars |
|---|---:|---:|
| `rsi_bearish_recovery` | 18,785 | 52.8% |
| `below_ema9` | 16,935 | 47.6% |
| `rvol_above_recent` | 13,718 | 38.6% |
| `below_vwap` | 12,901 | 36.3% |
| `rsi_thrust` | 7,982 | 22.5% |
| `atr_expansion` | 5,883 | 16.5% |
| `consecutive_down` | 3,704 | 10.4% |

**Score distribution**:

| Score | Bars | % |
|---:|---:|---:|
| 0 | 876 | 2.5% |
| 1 | 9,504 | 26.7% |
| 2 | 12,353 | 34.8% |
| 3 | 7,489 | 21.1% |
| 4 | 3,683 | 10.4% |
| 5 | 1,362 | 3.8% |
| 6 | 278 | 0.8% |
| 7 | 3 | 0.0% |

**Would-fire count at each MIN_CONDITIONS threshold** (after MIN_CORE_CONDITIONS=2 gate, which mirrors the live `MomentumStrategy.evaluate()`):

| Threshold | With core gate | % | Without core gate (diagnostic) | Δ confirmer-only |
|---:|---:|---:|---:|---:|
| ≥ 3 | 10,334 | 29.1% | 12,815 | 2,481 |
| ≥ 4 | 5,001 | 14.1% | 5,326 | 325 |
| ≥ 5 | 1,643 | 4.6% | 1,643 | 0 |  ← live
| ≥ 6 | 281 | 0.8% | 281 | 0 |

## Interpretation guide

- **A condition that fires on >70% of bars** is a free-score factor; the audit (§3.10) has historically dropped these (e.g. `stoch_rsi_not_overbought` in 0.7.1, `near_below_emas` in 0.7.2). Candidates for removal.
- **A condition that fires on <2% of bars** is a chronically-missing gate; if it's the difference between score=4 and score=5 (live threshold), the strategy is structurally unable to fire and the threshold should be either lowered OR the condition replaced.
- **Would-fire at threshold N**: if `would_fire_at[5]` is 0 but `would_fire_at[4]` is non-trivial, the audit's '0 fires' finding is a tuning issue, not an orchestration issue.

## Pair with Track D's instrumentation half

This analysis is one half of G.P0.11. The other half — instrumenting the live monitor to count `momentum.evaluate()` invocations vs fires — is tracked in issue #312 (Track D). Once that lands, comparing the live consideration count against this report's would-fire counts answers whether the discrepancy is a tuning issue (here) or an orchestration issue (there).
