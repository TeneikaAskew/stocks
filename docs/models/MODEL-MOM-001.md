# MODEL-MOM-001 — Momentum strategy

**Code:** `lib/strategies/momentum.py` (260 lines), thresholds in
`lib/strategies/config.py` ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-17

> **Read from the scoring functions, not the module docstring.** The first version of this
> document was assembled from `momentum.py`'s module docstring and was wrong in three ways
> — see [A warning about this module's own docstring](#a-warning-about-this-modules-own-docstring).

## What it decides

Per bar, per ticker: whether a CALL or PUT momentum signal is eligible to fire.
`CALL = buy strength` — the opposite call logic from [MODEL-MR-001](MODEL-MR-001.md),
which buys oversold dips.

## The firing rule: a scored gate, not a conjunction

**It is not "all conditions hold".** Seven conditions are scored one point each, and a fire
requires **both**:

| Gate | Value | Source |
|---|---|---|
| Total score | `>= MIN_CONDITIONS_MOMENTUM` = **5** of 7 | `config.py:108` |
| Core conditions among them | `>= MIN_CORE_CONDITIONS` = **2** | `config.py:127` |

Core conditions are the four structural ones — `consecutive_up`, `rsi_bullish_recovery`,
`above_vwap`, `above_ema9` (`config.py:129-134`; PUT mirrors at `:136-141`). So the three
newer confirmation factors cannot carry a fire on their own.

## The seven scored conditions (CALL; PUT mirrors)

| # | Condition name | Test | Threshold | Source |
|---|---|---|---|---|
| 1 | `consecutive_up` | `Consecutive_Up >= 3` | `CONSECUTIVE_PERIODS = 3` | `config.py:53` |
| 2 | `rsi_bullish_recovery` | `25 < RSI < 50` | `CALL_RSI_RANGE = (25.0, 50.0)` | `config.py:31` |
| 3 | `above_vwap` | `Close > VWAP` | — | `momentum.py:88` |
| 4 | `above_ema9` | `Close > EMA9` | — | `momentum.py:93` |
| 5 | `rvol_above_recent` | `RVol_Recent_20 > 1.2` | `RVOL_RECENT_THRESHOLD = 1.2` | `config.py:70` |
| 6 | `atr_expansion` | `ATR_Expansion > 1.15` | `ATR_EXPANSION_THRESHOLD = 1.15` | `config.py:78` |
| 7 | `rsi_thrust` | `RSI_Thrust_3 > 5.0` | `RSI_THRUST_THRESHOLD = 5.0` | `config.py:88` |

Conditions 5–7 are NaN-guarded: a missing indicator scores zero rather than raising or
defaulting true (`momentum.py:99-112`).

**`StochRSI` is not scored — but it still decides whether the bar is evaluated at all.**
It was removed as a *condition* in Phase 0.7.1, and the function docstring records why with the
measurement: *"`stoch_rsi_not_overbought` (StochRSI_K < 80) fired on 72.2% of bars — pure
free score that didn't discriminate setup quality"* (273 morning bars, 2026-05-01 strategy
audit). The **availability gate** on the same field was not removed — see below. The gate
outlived the factor.

## The availability gate — separate from the score

Before any condition is scored, `MomentumStrategy.evaluate` returns `None` outright when either
indicator is NaN (`momentum.py:190-195`):

```python
        # Skip warmup bars where indicators are still NaN.
        rsi_val = row.get(_rsi_col_name(), row.get("RSI14"))
        if pd.isna(rsi_val):
            return None
        if pd.isna(row.get("StochRSI_K")):
            return None
```

So a bar can satisfy the 5-of-7 floor *and* the 2-core-condition rule and still produce
nothing. This is not the same as the soft NaN handling documented for conditions 5-7, which
scores zero and continues (`momentum.py:99-112`); this aborts.

**Whether that is reachable depends on which implementation runs**, and the answer is not the
same for both:

| Path | Guard | Reachable? |
|---|---|---|
| `MomentumStrategy.evaluate` under the live engine | `momentum.py:190-195` | **No.** `lib.indicators` `fillna(50.0)`s RSI (`:50`) and fills `stoch_rsi` before the 3-bar rolling mean (`:85`), so `StochRSI_K` is NaN on bar indices **0-1 only**, and `min_bars_for_signals = 30` (`lib/config.py:192`) means the evaluated bar is always index ≥ 29 |
| `MarketAnalyzer.generate_technical_signals` | `lib/trading_analysis.py:817-819` | **Yes.** It carries its own indicator math with no `fillna` (`:242-245`, `:335-336`), so `StochRSI_K` is NaN on indices **0-15**, while its loop starts at bar 3 (`:810`). Bars 3-15 are skipped |

Measured on a 60-bar series. `MarketAnalyzer` is the path
`scripts/run_historical_signals.py:40` uses to populate `historical_signals`, so the two halves
of that table — live rows and backfilled rows — disagree about warm-up bars. Whether
backfilled and live-generated signals over the same bars are statistically interchangeable is
already an open decision in
[15-OPEN-DECISIONS](../product/15-OPEN-DECISIONS.md); this is evidence for it.

An earlier revision of this document described the scored conditions and the runtime layer and
said nothing about the bar on which the strategy declines to run. Recorded as DOC-29.

Per-ticker RSI ranges override the Tier-B default via
`lib.strategies.calibration.get_call_rsi_range(ticker)`, written by
[MODEL-CALIB-001](MODEL-CALIB-001.md) — the percentile calibrator, which **no experiment evaluates**. Read that document
before treating a calibrated range as validated.

## Entry points

| Symbol | Role |
|---|---|
| `MomentumStrategy` (`lib/strategies/momentum.py`) | The live implementation: `gcp/signal_monitor.py:1095` calls `MOMENTUM.evaluate` on every bar |
| `MarketAnalyzer.generate_technical_signals` (`lib/trading_analysis.py:784-918`) | **A second, inline implementation — not a wrapper.** It neither imports nor calls `MomentumStrategy`; it scores its own seven conditions in its own loop with its own literals, `min_conditions = 5` and `min_core_conditions = 2` (`:896-897`), and resolves a both-eligible bar by strict comparison with a tie firing nothing (`:904-912`), mirroring `MomentumStrategy.evaluate` (`:217-223`). Historical-signal callers still invoke it directly |

An earlier revision of this document called the `MarketAnalyzer` path "a back-compat wrapper
that delegates here". It does not delegate; it duplicates, and the two must be kept in
parity by hand. That is the debt [#285](https://github.com/TeneikaAskew/stocks/issues/285)
tracks ("decommission `lib/trading_analysis.py` momentum inline path or route through
`MomentumStrategy`"), open as of 2026-09-17.

## Rationale

**Partly recorded, and better recorded than most models here.**

- **`MIN_CONDITIONS_MOMENTUM = 5`** — `config.py:97` attributes it to a *"B+ 2026-05-06
  score-bucket walk-forward"*. That is a real derivation, though this document has not
  re-measured it.
- **Dropping StochRSI** — derived, with the 72.2% fire-rate measurement quoted above.
- **`consecutive_up` is strict 3-of-3, and the reversion is measured.** `_check_call_conditions`
  reads `Consecutive_Up >= CONSECUTIVE_PERIODS` (`momentum.py:78`) — the 3-bar column, not the
  5-bar `Consecutive_Up_5` that `lib/indicators.py:1141` still computes. The Phase 0.7.2
  3-of-5 relaxation (`CONSECUTIVE_WINDOW = 5`, `CONSECUTIVE_THRESHOLD = 3`, `config.py:61-62`)
  was reverted, and `config.py:101-103` records why: *"PR-1's walk-forward showed the 3-of-5
  relaxation regressed mean returns on both datasets while inflating fire counts ~3x"*. The
  two constants survive in `config.py` with no reader outside that file, and the function
  docstring at `momentum.py:57` / `:121` still says "relaxed ... to 3-of-5" — a further stale
  line, added to DOC-18.

**UNKNOWN — not recorded in code or tests:** the `(25, 50)` RSI band, `MIN_CORE_CONDITIONS = 2`,
and the three newer thresholds `1.2` / `1.15` / `5.0`. Each is stated as a constant with a
short label and no derivation.

## A warning about this module's own docstring

`momentum.py`'s **module** docstring (lines 1-20) describes the Phase 0.8 extraction and has
not tracked the code. It lists five conditions including `StochRSI < 80`, which was later
dropped, and omits the three that were added. The **function** docstring at `:55-74` is
current and records each change.

Worse, that function docstring contains two stale lines of its own — *"Seven conditions total;
min_conditions=3 still gates fires"* (`:67`) while `config.py:108` sets
`MIN_CONDITIONS_MOMENTUM = 5`, and *"relaxed `consecutive_up` from 3-of-3 to 3-of-5"* (`:57`)
while the body reads the 3-of-3 column (`:78`) and `config.py:101-103` records the reversion.
Prefer `config.py` and the scoring body over either docstring.

Recorded as DOC-18 in
[07 § Documentation coverage](../product/07-MODEL-REGISTRY.md#documentation-coverage-and-freshness).

## Tests

`tests/lib/test_strategy_momentum.py` · `test_strategy_interface.py` ·
`test_strategy_isolation.py` · `test_strategy_legacy_parity.py` ·
`test_strategy_timeframe.py` · `tests/gcp/test_signal_monitor_standalone_momentum.py` ·
`tests/gcp/test_signal_monitor_momentum_instrumentation.py` ·
`tests/scripts/test_momentum_eligibility.py`

## Known issues

[#285](https://github.com/TeneikaAskew/stocks/issues/285) duplicate inline path · [#701](https://github.com/TeneikaAskew/stocks/issues/701) two divergent voters · [#1137](https://github.com/TeneikaAskew/stocks/issues/1137) the module docstring describes behaviour the code no longer has.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
