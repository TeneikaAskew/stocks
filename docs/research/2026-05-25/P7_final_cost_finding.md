# Phase 7 — Final verdict: the historical backtest was gross-of-cost

**Date:** 2026-05-25
**Reviewer thesis:** *"Every entry tested in this entire thread produced a gross edge below cost. The voter result is not a new problem; it's the same problem now visible in your live signal."*

## THE FINDING

**`BACKTEST_RESULTS.md` was computed gross of transaction costs.** The +133% Sharpe lift / Sharpe 0.43 for the Strat-overlay strategy was a costless-fantasy artifact, not a deployable result.

### Evidence

From `BACKTEST_RESULTS.md` legend (line 156):
> **Avg Win / Avg Loss** | Move on the *underlying* (not options)

From the IWM Strat-overlay row (line 38):
> Trades 12,238 | Win rate 41.4% | Avg Win +0.29% | Avg Loss -0.20% | **Expectancy +0.003%**

Doing the math:
- Expectancy gross = `0.414 × 29 - 0.586 × 20` = **+0.3 bps/trade**
- 10 bp round-trip cost → **-9.7 bps net/trade**

What our 5-month OOS holdout produced under the SAME rulebook ladder:
- IWM 60m strength≥3: net **-9.37 bps/trade** (n=845, CI [-10.75, -8.00])

**Identical to within 0.3 bps.** The OOS isn't a regime anomaly — it's the cost reality the backtest hid. There was never positive net expectancy to begin with.

Zero mentions of `cost`, `commission`, `slippage`, `fee`, `spread`, or `transaction` anywhere in `BACKTEST_RESULTS.md`. The Sharpe is Sharpe-of-gross-returns. The +133% lift moved Sharpe from 0.19 (also gross) to 0.43 (also gross). Net Sharpe of both modes is approximately 0 or negative.

## Through-line across the entire P7 audit

Every entry signal tested produced gross-of-cost edges below the 10 bps round-trip cost line:

| Signal | gross/trade | cost | net/trade |
|---|---|---|---|
| Classifier (D10 long, IWM 15m, structural R=3) | +7-8 bps | 10 bps | -2 to -3 |
| Combo × regime (n≥500 cells) | +3 to +5 bps | 10 bps | -5 to -7 |
| **Production voter (momentum, all strength floors)** | **+0.3 to +0.6 bps** | 10 bps | **-9 to -12** |

The production voter is the WORST of the three signals tested. It's not a bug, it's the system's design point hidden by the gross-of-cost backtest.

## What the segmentation confirmed (and didn't)

### Strength is the sizing field — confirmed
- `scripts/run_historical_signals.py:318` → `'signal_strength': int(sig['total_score'])`
- So `signal_strength` IS the rulebook's 0-8 sizing score, NOT just `base_score` (0-5)
- Strength sweep shows: net −9.37 (≥3) vs −9.19 (≥5) — sizing up is sizing into trades that aren't better
- **Action: flatten the score-to-size ladder to constant until some score field is proven to rank EV**

### Strategy segmentation — unfalsifiable
- `historical_signals.strategy` has only ONE value: `momentum`. Can't segment.

### Time-of-day segmentation (rulebook §4 windows) — all negative

Best TOD bucket per cell, net/trade (all OUT 0):

| ticker × tf | best TOD | n | net/tr | win% | rulebook says |
|---|---|---|---|---|---|
| IWM 60m | 11:30-13:30 lunch | 261 | -8.76 | 45.6% | size ×0.5 (avoid) |
| SPY 60m | 14:00-16:00 degraded | 268 | -9.11 | 49.6% | size ×0.5 (discouraged) |
| QQQ 60m | 14:00-16:00 degraded | 256 | -9.44 | 49.6% | size ×0.5 (discouraged) |

**The rulebook's TOD ordering is inverted in this data.** The "degraded" 14:00-16:00 window has the highest win rates (45-50%) and the least-negative gross. The "prime" 9:30-11:30 window is the worst across SPY/QQQ. Recommend re-checking the rulebook's TOD size modifiers against this data before locking decisions.

But even the best TOD bucket nets -8.76 to -9.44. The rulebook's TOD multipliers can't multiply UP a strategy that's negative everywhere.

### RSI exit is dead — confirmed
- 0.4-2% of trades exit via RSI extreme. Effectively never fires on 30-35 min holds.
- **Action: drop the RSI rule from the exit ladder OR redefine its trigger (e.g. RSI on entry TF instead of trade TF, or RSI delta from entry).**

## What this thread actually settled

| Question | Answer |
|---|---|
| Is the next-candle classifier deployable as an entry signal? | **No** — gross +7-8 bps below 10 bp cost |
| Do combo × regime cells make money OOS? | **No** — trustworthy cells have +3-5 gross |
| Does the classifier overlay save a losing voter? | **No** — voter is too negative for any filter lift to clear costs |
| Does the rulebook exit ladder save the voter? | **No** — net -9 to -12 across every cell |
| Does higher voter strength rank EV? | **No** — sizing field doesn't differentiate |
| Does TOD segmentation surface a positive cell? | **No** — every TOD × ticker × TF is OUT 0 negative |
| **Was the historical +133% Sharpe net of costs?** | **No** — and that's the whole story |

## What to do next

Per the reviewer, three actions follow from this verdict:

### 1. Stop tweaking the current voter
There is no exit-rule tuning, strength threshold, or TOD filter that will make a +0.3 bps gross signal net-positive against a 10 bp round-trip. This is settled — high statistical confidence (SE ≤ 1.4 bps per cell, n > 500 per cell).

### 2. Flatten the sizing ladder
Until ANY score field is proven to rank EV, the score-to-size ladder is sizing up into equivalent trades. Use constant sizing. Re-test the ladder only after a candidate score field shows EV stratification.

### 3. Rebuild voter v2 with cost-aware backtesting from the start
Any next-iteration signal MUST be backtested net of:
- 10 bp ETF round-trip for ETF positions, OR
- 7-15% premium round-trip for 0DTE options (which is the user's actual instrument)
- And reported with both gross and net per-trade P&L, plus 95% CI

The +133% Sharpe trap should not be repeatable. Recommend adding a cost-assumption block to the top of `BACKTEST_RESULTS.md` and a mandatory net-P&L column to all future per-strategy tables.

### 4. Skip avenue 2 (wider stop)
Reviewer is right: the 34% time stops average ~+4 bps, meaning entries barely drift favorable. Widening the stop lets weak drifters survive longer but can't manufacture +30 bp moves, and raises the break-even target rate. Don't bother.

## Cost

- Strategy probe + TOD segmentation rebuild: ~$0.50
- **Cumulative Phase 7 session: ~$22**

## Artifacts

- `gcp/research/p7g_voter_rulebook_sweep.py` — sweep with TOD breakdown
- `gs://.../research/p7g/{ticker}_{tf}_rulebook_*.json` — per-cell detailed results
- `BACKTEST_RESULTS.md:156` — the gross-of-cost legend that hid the issue

## Lesson

The single most important lesson of Phase 7: **always check whether a backtest is gross or net of costs before quoting a Sharpe.** The cost line is the difference between research candy and a deployable strategy, and it's invisible in any framework that doesn't deduct it.

Concretely, before any future per-strategy reporting:
1. Top of doc states the cost assumption in basis points
2. Every per-trade P&L table has BOTH `avg_gross` AND `avg_net` columns
3. Sharpe is reported on net returns only
4. If the strategy is on options not the underlying, the cost line is the option round-trip not the ETF round-trip (typically 3-5× higher)
